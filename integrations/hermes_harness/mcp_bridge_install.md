# Bridge release install runbook (BR2, `menu` action, compat admission) — mmx-browser MCP server

Build/checkout commit `NEW = 920544c6bc98f5bfd403ad7baf73968ec1d89935` on branch
`t3/mmos-v4-br2`, rollback release `OLD = b640dec1461a29cd5e42910c992973f50597d93f`
throughout. This runbook's own commits (the BR2 review fixes and this slide) sit
atop `NEW`. They touch no protocol source — the MED-1 fix is in the extension's
`browser_control.js`, LOW-1 in `runtime_pin.py`, LOW-2 a comment, MED-2 this
document — so an install run from the branch head re-curates step 1's manifest at
its own head and the installed `release_commit` is that head, not `920544c6b`.
That does not move the transport compatibility constants: the three step-1
runtime hashes and `EXPECTED_CAPABILITY_DIGEST = "08c66c33…"` hold unchanged at
the branch head, and the compat admission window is identical. The full rehearsed
step list (ruling 16 output + ruling 17 table) is mirrored at
`integrations/hermes_harness/br2_step_list.md` and
`~/.mastermind/mmos_evidence/br2-20261114/STEP_LIST.md`.

## Install-sequencing precondition the principal must read first (live state)

BR2's compat window admits **exactly one previous release: b640dec1**
(`PREVIOUS_TRANSPORT_CAPABILITY_DIGEST = 1c40ec98…`). It does **not** admit the
release before that (`5aa30969`, digest `e0216d3d…`). As of this staging the live
flat pin is still `5aa30969241163b4abb3e025bc9e52123ee4b478` (40 actions,
`e0216d3d…`) and the loaded extension folders are still the `0.4.0` renders
(`e0216d3d…`): b640dec1 is installed-but-NOT-switched (its release root exists and
its install step 2 ran — `br-install-20261112b/RESULT.md` — but the pin switch and
the Chairman's five extension reloads are still pending).

Consequences (ruling 17 fixes the admitted previous to one named release):

- A BR2 host **refuses** a peer presenting `e0216d3d…` (today's loaded `0.4.0`
  extension and today's live-pin client). A BR2 extension (`08c66c33…`) is
  **refused** by a b640dec1 host (which admits `1c40ec98…` + `e0216d3d…`).
- Therefore BR2 **cannot** be switched in directly over the current
  `5aa30969`/`0.4.0` fleet without a breakage window: the not-yet-reloaded `0.4.0`
  profiles would meet a BR2 host that does not admit their digest.

**Safe sequencing (the principal's decision):** complete b640dec1's sitting first
— the five reloads to the b640dec1 extension (`1c40ec98…`, folder
`~/Downloads/Mastermind-Browser-0.6.0-b640dec1`) and the pin switch to b640dec1 —
so the whole fleet is uniformly on b640dec1, **then** run the BR2 steps below over
b640dec1 (its admitted previous). Every step and table in this runbook assumes
that precondition: step 0 verifies it. The window below is proven for the
**b640dec1 → BR2** hop, which is the hop BR2's admission covers. Install and pin
switch are the principal's; this runbook stages nothing live.

## Why compat admission exists (the release-3 lesson BR2 inherits)

`transport_capability_digest()` (`integrations/chairman_surfaces/web_sol_protocol.py`)
hashes the document that includes `"browser_actions": sorted(browser.ACTIONS)`.
Release 3's first install attempt (2026-11-12) copied 15 files into a new release
root, changing **only the client side**; the native hosts Chrome spawns kept
importing protocol code from the old root, computed the old digest, and
`_accepted_peer_hello` (`_web_sol_native_host_impl.py`) raised
`transport_capability_mismatch` and dropped the connection before the ack — which
the client reports as `transport_handshake_failed` (every local profile failed at
step 5; rolled back). The fix, proven in release 3 and inherited unchanged by BR2:
the host admits **exactly two** digests (its own and the immediately previous
release's), holds an old-digest connection to the old action set, and the pin
switch is last so no running session ever meets a host that refuses it.

BR2's digest delta is the `menu` action:

- a client (bridge) at `NEW` computes digest
  `08c66c330c9d3cd6728ff67628aa314afd446389b6bd394a93a9f8b63672a05a` (42 actions);
- a client at `OLD` (b640dec1) computes
  `1c40ec98d1086a8f8005151757b040698057019f5e9169cace91e393b6f60d40` (41 actions);
- `WEB_SOL_PACKAGE_VERSION` is `0.4.0` on both sides, so the version check never
  fires — only the digest differs. The delta is exactly **+`menu`**.

## What BR2 changes: previous-release admission and per-connection action sets

The host admits exactly two digests: its own and the immediately previous
release's, as a named constant next to the commit it belongs to
(`PREVIOUS_TRANSPORT_CAPABILITY_DIGEST = 1c40ec98…`,
`PREVIOUS_TRANSPORT_CAPABILITY_RELEASE_COMMIT = b640dec1…` in
`web_sol_protocol.py`; no wildcard, no "any older" — any third digest is refused
at the handshake, and a foreign extension presenting one exits 65).

A connection admitted on the old digest is **held by the host to the old action
set** (`web_sol_browser_protocol.PREVIOUS_ACTIONS`, the 41 old actions —
everything except `menu`). A request for an action outside the set the connection
presented — whatever the client sends — is answered with an explicit
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
(`_accepted_transport_ack`: the ack's `capability_digest` must equal the client's
own computed digest) passes against the new host's answer. This is proven at
protocol level by the slid compat suite (`tests/test_web_sol_transport_compat.py`,
11/11: old client admitted, `menu` refused without forwarding, old extension holds
`menu` back from a new client, third digest refused at the handshake).

## What Chrome reads from disk after load, and the staging method

An unpacked extension is **not** a snapshot: Chrome keeps reading the loaded
folder's bytes after installation.

- `background.js` is an MV3 service worker. Chrome suspends and kills it on idle
  and re-runs it on every wake; each wake re-executes its
  `importScripts("instance_config.js", "census_core.js", "browser_cdp.js",
  "browser_control.js")` **from disk**.
- `content.js` is declared in `manifest.json` `content_scripts`; Chrome reads it
  from disk at **every injection** (each navigation of a matched page).
- `browser_page.js` is injected on demand via
  `chrome.scripting.executeScript({files:["browser_page.js"]})` — read from disk
  **per action**.
- `browser.html` (options) and `census.html` (popup) load their scripts from disk
  when opened.

So copying new bytes into a folder Chrome has already loaded takes effect with no
person acting: the next service-worker wake runs new worker code, the next
navigation injects a new page script, and between the copy and a deliberate reload
a profile can momentarily mix an old worker closure with new page bytes. That is
why release 2's step "pre-update the staging folders" is **deleted**: it copied new
bytes into the loaded folders and left the mix to chance until each reload.

The method instead: **the bytes of a folder Chrome has already loaded are never
changed by any step.** The installer stages each profile's render into a **fresh
per-release staging root** (`--staging-root
~/Downloads/Mastermind-Browser-0.6.0-920544c6b/Chrome-<alias>`, created by the
installer; it must not be a folder any Chrome has loaded), and its default
`update_loaded=False` skips the loaded-folder rewrite entirely (the rewrite exists
only behind an explicit `--update-loaded` flag for a requested in-place update).
The profile is moved to the new bytes only by the operator's step 3 below: remove
the extension and Load unpacked from the new staging folder.

What that does to identities: nothing. The extension id
`kmpbpccecbofdnhpcmjogofgmdodpnko` is derived from `manifest.json`'s `"key"` (not
from the folder path), so loading from a different folder keeps the id, and the
native hosts' manifests' `allowed_origins`
(`chrome-extension://kmpbpccecbofdnhpcmjogofgmdodpnko/`) stay valid with no
registration change.

**What remove+load does to state (BR2 — true statement, replaces release 3's "no
`chrome.storage`"):** BR2 adds the `storage` permission and uses
`chrome.storage.session` for the item-3 opener records (`mmxOpenerRecords`) and the
session activity ledger. `chrome.storage.session` is cleared when the extension is
removed, so **remove+load clears every bridge opener record**. The consequence is
fail-closed and safe: after a reload, a tab the bridge opened before the reload no
longer has a record, so a bridge `close` of it is refused with
`TAB_NOT_BRIDGE_OPENED` and the tab must be closed by hand. Records rebuild on the
next bridge `open`. No operator tab or live-session tab ever becomes closable by
this loss — the only direction is record loss → refusal, never an unsafe close.
The activity ledger likewise restarts empty (a session re-earns its live lease on
its next accepted request).

## Why "no daemon restart needed" was wrong, and the versioned-runtimes fix

`server.js` captures `runtime.json`'s bytes at startup and re-verifies them before
**every dispatch**. Editing the live `~/.t3/mcp/mmx-browser/runtime.json` in place
makes every already-running server answer `REFUSED / NATIVE_SOURCE_CLOSURE_STALE`
(retry not allowed) until its session restarts — during release 3's first attempt
that hit 31 running servers.

Therefore: **never edit the live `runtime.json`.** This runbook switches releases
with versioned runtime folders plus a `current` symlink; `server.js` is
byte-identical everywhere and no pinned file ever changes under a running server.
The BR2 rehearsal proved a server started through `current/` keeps answering, on
its original commit, across a symlink repoint, while the next server spawned
through `current/` resolves the new release (`br2/rehearsal/logs/rehearsal_switch.log`).

## What a release folder must contain and how it is built

A release root (`~/.local/share/mastermind-browser-control/releases/<commit>/`)
built by `integrations/hermes_harness/install_browser.py` holds ~155 files:

- the **pinned source closure** from the build manifest (70 files at this head:
  `integrations/chairman_surfaces/` incl. the 16 `web_sol_extension/` sources,
  `integrations/hermes_harness/` incl. `browser_plugin/`, `control_plane/`,
  `docs/`, `tests/`);
- `BUILD.json` — the manifest the installer wrote (commit + file→sha256 map);
- **generated per profile**: `chrome/<Profile-N>/bin/<host-id>` (the `sh` wrapper
  that `cd`s into the release root and execs the pinned python),
  `chrome/<Profile-N>/native-hosts/<host-id>.json`, and
  `chrome/<Profile-N>/extensions/<id24>/` (13 rendered files).

**Known gap (report, not fixed here):** `build_browser.py` hashes every tracked
file at HEAD with a 300-file cap; the repo has grown past that, so it refuses
(`invalid source closure`). Until that is repaired, the manifest is curated from
the `OLD` (b640dec1) `BUILD.json`: keep every path that still exists, re-hashed at
`$NEW`, drop paths that no longer exist (none at this head), add the new BR2 tests.
The exact command is step 1 below and reproduces the used manifest bit-for-bit
(70 files = 65 kept from b640dec1 + 5 new BR2 tests).

## Install steps — order matters: build, reload, switch the pin LAST

`BASE=~/.local/share/mastermind-browser-control`,
`STAGING=~/Downloads/Mastermind-Browser-0.6.0-920544c6b`,
`MMX=~/.t3/mcp/mmx-browser`. The installer is run from the repo root checked out at
`$NEW` (it stages from the checkout; run it as a module, not a path). Check after
every step; every step has a rollback.

0. **Preconditions.** Pick a quiet window. **Verify the sequencing precondition
   above: the whole fleet is uniformly on b640dec1** — the live pin
   (`readlink $MMX/current` or the flat `runtime.json` `release_commit`) is
   `b640dec1…`, and all five profiles are loaded from
   `~/Downloads/Mastermind-Browser-0.6.0-b640dec1` (their `background.js`
   `EXPECTED_CAPABILITY_DIGEST` = `1c40ec98…`). If any profile is still on `0.4.0`
   (`e0216d3d…`) or the pin is still `5aa30969…`, **stop**: complete b640dec1's
   sitting first. Nothing below writes to a Chrome profile directory or to any
   extension folder a Chrome has loaded. `STAGING` must not exist yet (the
   installer creates it; if a previous attempt left one, move it aside — the
   prepared guard refuses changed bytes in an existing folder, which is the guard
   working). The enrollment file
   (`~/.mastermind/mmos_evidence/br-20261111/release2/enrollment.json`, sha256
   `5cef20bf0382127876667cbac4021fc2064dc86394b6346faffc619a5ccf177a`, reused by the
   b640dec1 install) must still match the live `deployments-v2.json` rows (6 local
   profiles, 2 ssh hosts); re-derive it if rows changed.

1. **Stage the tree and curate the build manifest** (until `build_browser.py`'s cap
   is repaired). Check out `$NEW` in the work tree. Check: `git rev-parse HEAD` =
   `$NEW` (or the branch head whose transport constants match); `shasum -a 256` of
   the changed runtime files equals
   `755c094955b08c97d54b2bce89c88e9e33e42ecc61247c33cb01b25f2319e824`
   (`web_sol_browser_protocol.py`),
   `f1d78a60343c113ea01fef399ec93cd0b6da461c7b944bf932524cc4f4788d18`
   (`browser_bridge.py`),
   `c34bf7a30383a6eab3079259e6d9333d4dc8be179565b7a104d86860308cdf55`
   (`browser_tool_schema.json`); `background.js` pins
   `EXPECTED_CAPABILITY_DIGEST = "08c66c33…b63672a05a"`. Then:

   ```bash
   python3 - <<'EOF'
   import json, hashlib, pathlib
   ROOT = pathlib.Path(".")                     # repo root at $NEW
   OLD = "b640dec1461a29cd5e42910c992973f50597d93f"
   NEW = "920544c6bc98f5bfd403ad7baf73968ec1d89935"
   BASE = pathlib.Path.home()/".local/share/mastermind-browser-control"
   old = json.load(open(BASE/f"releases/{OLD}/BUILD.json"))["files"]
   sha = lambda p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
   files = {p: sha(p) for p in old if (ROOT/p).exists()}
   files.update({p: sha(p) for p in [
       "tests/browser_menu_playwright.cjs",
       "tests/browser_snapshot_ensure_playwright.cjs",
       "tests/browser_orphan_close_contract.cjs",
       "tests/test_web_sol_browser_menu_ensure.py",
       "tests/test_web_sol_transport_gates.py"]})
   json.dump({"schema": "mastermind.browser_direct_build.v1", "source_commit": NEW, "files": files},
             open("BUILD-920544c6b.json", "w"), indent=2, sort_keys=True)
   print(len(files), "files")
   EOF
   ```

   The schema string must be exactly `mastermind.browser_direct_build.v1`
   (`install_browser.py` refuses anything else) and the filename must be
   `BUILD-920544c6b.json` — step 2 reads that exact name. If installing from the
   branch head, `$NEW`, the manifest filename and `source_commit` are that head's
   values instead. Check: `70 files`; the three hashes above appear in it.
   Rollback: `git checkout` back, delete the file. Nothing else changed.

2. **Build the release and register the hosts** (the installer). This builds the
   full release folder, stages every profile's render under `STAGING`, and
   re-registers every profile's Chrome `NativeMessagingHosts` manifest into the new
   release root. From this moment any host respawn runs new host code — which is
   safe at every moment below precisely because the new host admits the previous
   release's digest (compat admission, proven by the slid compat suite):

   ```bash
   python3 -m integrations.hermes_harness.install_browser \
     --build-manifest BUILD-920544c6b.json \
     --install-base ~/.local/share/mastermind-browser-control \
     --python ~/.hermes/tools/python-3.14.9+20261021-darwin-arm64/bin/python3.14 \
     --enrollment ~/.mastermind/mmos_evidence/br-20261111/release2/enrollment.json \
     --staging-root ~/Downloads/Mastermind-Browser-0.6.0-920544c6b \
     --prior-source b640dec1461a29cd5e42910c992973f50597d93f
   ```

   `--staging-root` names the fresh per-release staging tree; without
   `--update-loaded` (default) the installer never rewrites a folder Chrome has
   loaded. The enrollment keys must be exactly
   `{host_ref, label, profiles, remote_hosts, remote_profiles}`. Check: stdout JSON
   `state` = `INSTALLED_PENDING_CHROME_LOAD`, `source_commit` = `$NEW`, all six
   `chrome[]` rows `ok: true`, every loaded row `activation: CHROME_RELOAD_REQUIRED`;
   the release folder holds ~155 files incl. `BUILD.json`; `bin/<host-id>` scripts
   `cd` into `releases/$NEW`; `STAGING/Chrome-<alias>/instance_config.js` carries
   digest `08c66c33…`; the manifest permissions include `storage`; the loaded
   `0.6.0-b640dec1` folders are byte-identical to before the run (`shasum -a 256` a
   folder before and after).
   Rollback (complete undo — the installer cannot rebuild `OLD` from a `$NEW`
   checkout, so do not rerun it with `--prior-source $NEW`): for every
   `.previous.<16hex>` file the installer left under `BASE` and under
   `~/Library/Application Support/Google/Chrome/NativeMessagingHosts`, move it back
   over the file it backs up; then delete the new-only files: `releases/$NEW/`,
   `installation-$NEW.json`, `packages/$NEW/`, `STAGING/`. Restore
   `deployments-v2.json` from its own `.previous` backup the same way. The `OLD`
   release directory is never modified by any step.

3. **Operator extension reloads, profile by profile** (human/operator action;
   ChatGPT1-4 and personal-default; `mastermindx` has a pre-existing
   `PROFILE_IDENTITY_MISMATCH` unrelated to this release). **⟳ alone is not
   enough** — it re-reads the *old loaded folder*, whose bytes step 2 deliberately
   never changed. For each profile, in `chrome://extensions`: remove the Mastermind
   extension, then Load unpacked from `STAGING/Chrome-<alias>`. The id and
   `allowed_origins` are unchanged (the manifest `key` derives the id). **Remove+load
   clears `chrome.storage.session`** (the item-3 opener records and activity ledger):
   bridge-opened tabs from before the reload then refuse close with
   `TAB_NOT_BRIDGE_OPENED` (fail-closed) and must be closed by hand; records rebuild
   on the next open. The removal drops the native-host connection so Chrome re-reads
   the `NativeMessagingHosts` manifest — now pointing into `releases/$NEW` — and
   spawns a new-code host. One profile at a time, confirming the previous one still
   answers (its next browser call) before moving on. Do all five; the loaded version
   string stays `0.4.1` — the observable change is the `menu` action. Every session,
   old-pin or new-pin, keeps working across each reload (window table below).
   Check per profile: reload done, `STAGING` folder is the loaded one.
   Rollback: repoint nothing yet — reload the profile back from its untouched
   `~/Downloads/Mastermind-Browser-0.6.0-b640dec1/Chrome-<alias>` folder (those bytes
   were never changed by any step, so they are the working state).

4. **Switch the pin — LAST.** By now every profile runs the new extension and a
   new-code host, and every session in the fleet still holds the old pin and works.
   The pin writer is `integrations/hermes_harness/runtime_pin.py` — guarded: no
   default root (`--mmx-root` is required), it never edits the flat live pin files,
   never writes inside the folder `current` resolves to, never overwrites a
   delivered `runtimes/<commit>` (ruling 19: a delivery mark is permanent), and
   switches only by atomic symlink replace. One O_EXCL delivery lock covers every
   delivery-mark writer under the root. Run from the repo root. First the one-time
   migration to versioned runtimes (zero behavior change; `current` → `OLD`):

   ```bash
   MMX=~/.t3/mcp/mmx-browser
   OLD=b640dec1461a29cd5e42910c992973f50597d93f
   NEW=920544c6bc98f5bfd403ad7baf73968ec1d89935
   python3 -m integrations.hermes_harness.runtime_pin migrate \
     --mmx-root $MMX --old-commit $OLD --new-commit $NEW \
     --build-manifest BUILD-920544c6b.json \
     --new-source-root ~/.local/share/mastermind-browser-control/releases/$NEW
   ```

   It delivers `runtimes/$OLD` (the verbatim flat pin plus a byte-identical
   `server.js` copy) and `runtimes/$NEW` (the pin updated to the new commit, the new
   source root, and the closure hashes `BUILD-920544c6b.json` pins), then points
   `current` at `OLD` atomically. The flat `$MMX/runtime.json` and `$MMX/server.js`
   are never edited, so every running server — which captured the flat pin at
   startup and re-verifies it before each dispatch — is untouched. If installing
   from the branch head, `$NEW`, the manifest filename and `--new-source-root` are
   that head's values instead. Check: stdout JSON `state` = `PIN_MIGRATED`;
   `readlink $MMX/current` ends `/runtimes/$OLD`; the flat pin files are
   byte-identical before/after; every `runtimes/*/runtime.json` is mode `0600`
   (`server.js` refuses group/world-writable pins with `NATIVE_SOURCE_UNSAFE`).

   Then switch the registered server path — do NOT hand-edit these files. Running
   sessions rewrite `.claude.json`, so a hand edit can lose a race either way; no
   source writer ever registered mmx-browser there. Use the guarded command: it
   checks all four provider homes (`experiential-claude`, `fabric-experiential`,
   `fabric-unified-router`, `fabric-anthropic-oauth`) BEFORE the first write — each
   `mcpServers.mmx-browser.args` must end exactly at the old flat `$MMX/server.js`,
   and the JSON-encoded old path must occur exactly once in each file's raw bytes
   (zero or several occurrences refuse the whole run as `OLD_VALUE_NOT_UNIQUE`
   before any write, in any home). The change itself is a raw-byte replacement of
   that one span: the file is never re-serialised, so key order, non-ASCII text,
   float spellings, the trailing-newline state and the file mode survive byte for
   byte, and the replaced bytes must re-parse to exactly the intended one-value
   change. Writes go through the owned CAS writer, so a file changed since its
   check refuses alone (`WRITE_RACE`, keeping the session's bytes, leaving no
   backup) and every landed write leaves a `.claude.json.previous.<16hex>` backup;
   a write error that is not a digest mismatch is reported as what it is
   (`WRITE_FAILED` with the errno name), never as a race. After a short wait it
   reads every switched file back, so a session that rewrote a file is reported
   (`READBACK_RACE_*`), not silently believed. It prints home names and status codes
   only — never contents. The written arg is the literal `$MMX/current/server.js`
   symlink path, so later migrations only re-point `current` and never touch these
   files again. The fifth home (`fabric-unified-router-worker`) carries no entry and
   is never written; an entry there refuses the whole run.

   ```bash
   python3 -m integrations.hermes_harness.mmx_provider_registration \
     --providers-root ~/.t3/providers --mmx-root $MMX
   ```

   Check: stdout JSON `state` = `PROVIDER_ARGS_SWITCHED`, one row per home
   (`SWITCHED`, or `ALREADY_SWITCHED` on a re-run — already-switched homes are
   no-ops, so one re-run after a race is safe). Each `.claude.json` parses and its
   last arg is `current/server.js`; a fresh session's read-only `browsers` (no
   probe) still shows `bridge_release_commit` `b640dec1…`. If `state` =
   `PROVIDER_ARGS_SWITCHED_WITH_RACES`, or the command refuses (it names the home
   and a code), re-run ONCE when the racing session is idle — do not loop; a refusal
   means the files are not in the expected state and must be diagnosed, not retried
   blindly. Then the atomic repoint:

   ```bash
   python3 -m integrations.hermes_harness.runtime_pin switch --mmx-root $MMX --commit $NEW
   ```

   Check: stdout `state` = `PIN_SWITCHED`; a fresh session shows
   `bridge_release_commit` `920544c6b…` and the actions enum has `menu` (45 actions
   = 42 browser + 3 local); the old sessions keep answering on `b640dec1…` —
   rehearsed: same server, same commit and action set before and after the repoint
   (`br2/rehearsal/logs/rehearsal_switch.log`).
   Rollback: the same `switch` command with `--commit $OLD` — one atomic repoint, no
   rewrite. To undo the whole migration instead: restore the four
   `.claude.json.previous.<16hex>` backups the guarded switch left (one per provider
   home) so spawns use the flat `$MMX/server.js` again, and LEAVE `runtimes/` and
   `current` in place — deleting them would break any server spawned via
   `current/server.js`, which re-verifies `runtime.json` from its own folder on every
   dispatch. Running sessions are untouched either way.

5. **Verify in a fresh session** (read-only):
   - `browsers` with `probe: true`: the five local profiles `CONNECTED`,
     `bridge_release_commit` `920544c6b…`;
   - actions enum: 45 entries incl. `menu`;
   - `status` shows the new commit;
   - one old session (started before step 4, if any is handy) still answers
     `browsers`/`status` on the old commit — its `menu` is absent, which is correct
     for its pin.
   Rollback: steps 4 → 3 → 2 in reverse order.

## Rollback window

Per step: what is actually live once the step is done, how to undo exactly that
step, and until when that undo is the right one (MED-2: a bare pin rollback with no
procedure strands every profile reloaded at step 3 — after the reload those
extensions present the NEW digest, and the OLD host is single-digest-strict, so the
truthful rollback names the reverse reload and the order). Roll back in reverse
step order; the OLD release directory and the old loaded `0.6.0-b640dec1` folders
are never modified by any step, so the bytes every undo needs always exist.

| Step | What is live | How to undo | Until when |
| --- | --- | --- | --- |
| 1 | Nothing runtime-side: only the curated `BUILD-*.json` in the checkout; the OLD release, OLD pin and all loaded folders are untouched. | Delete the curated `BUILD-*.json`; `git checkout` the work tree back. No installed state exists yet. | Until step 2 consumes the manifest; after step 2, undo step 2 first. |
| 2 | New release root under `BASE`; every profile's `NativeMessagingHosts` manifest points into `releases/$NEW`, so any host respawn runs new-code (it admits the OLD digest); loaded extension folders are byte-identical; running sessions and old hosts are unchanged. | Restore every `.previous.<16hex>` backup the installer left under `BASE` and under `~/Library/Application Support/Google/Chrome/NativeMessagingHosts` (including `deployments-v2.json`'s own `.previous`), then delete the new-only files: `releases/$NEW/`, `installation-$NEW.json`, `packages/$NEW/`, `STAGING/`. | Only while no profile has been reloaded at step 3. After any step-3 reload, undo step 3 first (reverse reload): restoring the OLD host manifests under a profile running the NEW extension makes the OLD single-digest host refuse its handshake. |
| 3 | Per reloaded profile: NEW extension bytes plus a new-code host; the profile answers old-pin and new-pin sessions alike (compat admission). Not-yet-reloaded profiles are fully old. Every session keeps working throughout. | The reverse reload: in `chrome://extensions` remove the extension and Load unpacked from its untouched `~/Downloads/Mastermind-Browser-0.6.0-b640dec1/Chrome-<alias>` folder — those bytes were never changed by any step, so they are the working state. | Valid at any later point (the NEW host admits the OLD digest, and after a step-4 rollback the OLD host matches the old extension again); in a full rollback do it after undoing step 4 so the fleet stays uniform. |
| 4 | New spawns resolve `current` → `runtimes/$NEW` (new commit, `menu` present); providers' `.claude.json` args point at `current/server.js`; every running session keeps its already-resolved OLD files and answers unchanged. | The same atomic repoint back: `runtime_pin switch --mmx-root $MMX --commit $OLD`. To undo the whole migration instead, restore the four `.claude.json.previous.<16hex>` backups the guarded switch left (one per provider home) and LEAVE `runtimes/` and `current` in place — deleting them breaks servers spawned via `current/server.js`, which re-verify their folder's `runtime.json` on every dispatch. | Until step 5 verifies and the fleet has run the release; once the NEXT release replaces the compat-admission window (it admits only one previous digest), `$OLD` is no longer a rollback target and the reverse reload of step 3 must target that release's OLD folders instead. |
| 5 | Everything: all five profiles reloaded, all new spawns on the NEW pin, old sessions draining on their resolved OLD files. | Nothing to undo — step 5 is read-only verification. On a failed check, roll back 4 → 3 → 2 in reverse order as above. | End of the install sitting; afterwards the window table above is history and the next release owns rollback. |

## The window table (every cell works; `menu` appears only where both ends describe it)

"Old-pin session" = any session whose server resolved `current` (or the direct
path) before step 4's repoint (b640dec1 pin, `1c40ec98…`, 41 actions); "new-pin
session" = a session whose server spawned after it (BR2 pin, `08c66c33…`, 42
actions). "Reloaded profile" = step 3 has moved that profile to the new extension
folder and a new-code host; "not-yet-reloaded" = step 3 has not reached it
(b640dec1 extension, `1c40ec98…`). `menu` absent means exactly that: old actions
all work, the `menu` action does not exist for that session (it never asks for it).
**This table is for the b640dec1 → BR2 hop** (see the sequencing precondition for
why the fleet must be on b640dec1 first).

| Moment | Session pin | Reloaded profile | Not-yet-reloaded profile |
|---|---|---|---|
| after step 2 (build+register) | old | — | works; host is old-code while alive, new-code on respawn — either admits the old digest; `menu` absent |
| during step 3, per profile done | old | works (new extension + new-code host, old client admitted on the previous digest); `menu` absent | works as the row above |
| after step 3, before step 4 | old | works; `menu` absent | none left — step 3 does all five |
| after step 4 repoint | old | works, unchanged; `menu` absent | none (by the step 3 gate) |
| after step 4 repoint | new | works; `menu` admitted and executed | none (by the step 3 gate) |
| step 5 verify | old / new | works / works + `menu` | none |

Two invariants make the empty cells structural, not luck: (a) the pin switch is
last, so no new-pin session exists while any profile is still on the old extension;
(b) step 3 completes every profile before step 4, so no new client can ever meet a
live old-code host process (the one combination the old host refuses, having no
compat admission). **The person-performed step (3, reload) comes before the step
that makes new sessions depend on it (4, pin switch)** — ruling 17 satisfied. If a
profile is skipped in step 3, stop before step 4 and finish its reload. A session
spawned at *any* moment resolves the pin that `current` held at its spawn — old pin
until step 4, new after — and every row above holds for it.

## Residual effects (honest)

- Old-pin sessions keep the old action set until they restart; their `menu` is
  refused with `ACTION_UNAVAILABLE` (never a handshake failure, never a broken
  connection). A restart moves them to the new pin.
- A third digest (anything but the current and previous release's) is refused at
  the handshake, and an extension presenting one exits 65 — by design. In
  particular `e0216d3d…` (the `0.4.0` release before b640dec1) is **not** admitted;
  the sequencing precondition exists for this reason.
- Remove+load at step 3 clears `chrome.storage.session`: bridge-opened tabs from
  before the reload refuse close with `TAB_NOT_BRIDGE_OPENED` (fail-closed) until
  closed by hand; opener records rebuild on the next open.
- `mastermindx` stays `PROFILE_IDENTITY_MISMATCH` as it is today.
- The extension manifest version intentionally stays `0.4.1`.

## Rehearsal record (scratch `~/.mastermind/mmos_dev/br2/rehearsal/`)

| what | result | log |
|---|---|---|
| pin-switch rehearsal (running b640dec1 server across the atomic repoint; next server resolves BR2) | server on `current`→b640dec1: 44 enum (41 browser + 3 local), `read` present, `menu` absent, commit `b640dec1…`, identical after the atomic repoint; next server via `current`: 45 enum incl. `menu`, commit `920544c6b…`; real MMX pin folder before==after (zero difference) | `logs/rehearsal_switch.log` |
| compat admission (protocol level, slid compat suite) | old client admitted on `1c40ec98…`; `menu` refused without forwarding; old extension holds `menu` back from a new client; third digest refused at handshake | `tests/test_web_sol_transport_compat.py` (11/11) |
| census/surface admission intersection + digest-swap refusal | LOW1/LOW2 fold-ins gated at both ends | `tests/test_web_sol_transport_gates.py` (13/13) |

The full rehearsed step list with the ruling-16 output verbatim and the ruling-17
table is `integrations/hermes_harness/br2_step_list.md` (mirrored at
`~/.mastermind/mmos_evidence/br2-20261114/STEP_LIST.md`).

Scratch boundary: no Chrome instance runs on the scratch instance ids, so the
reload journey (remove + Load unpacked) and step 5's five-profile `CONNECTED` proof
are the operator's on the real machine; the transport rows those steps rely on are
proven at protocol level by the pytest suites and the digest equality of the built
release is proven by computation. No transport probe, extension reload or host
restart was performed against any real profile during rehearsal.

## Operator call: paged whole-answer read (unchanged)

Tool `mmx_browser` (T3: `mcp__mmx-browser__mmx_browser`). First call (after
`snapshot` gives `snapshot_id` and the element `ref`):

```json
{"action":"read","browser_id":"<browsers>","connection_id":"<status>",
 "tab_id":0,"url_fingerprint":"<tabs>","snapshot_id":"<snapshot>","ref":"<element ref>","offset":0}
```

Loop while `next_offset` is not null, repeating with `offset` set to it; every other
argument identical — never skip or repeat a page (a skipped or repeated page
silently corrupts the transcript; there is no drift guard across pages). The reply
carries `content` (always untrusted text), `total_characters`, `next_offset` (null
at the end) and `content_is_untrusted: true`. Reads never consume the snapshot,
mutate, scroll or focus. Invalid offsets return `READ_OFFSET_INVALID`; a wrong
argument shape returns `INPUT_REFUSED`. Read-contract limits: the worker enforces an
800,000-byte `RESULT_TOO_LARGE` and the native host a 921,600-byte `MAX_MESSAGE_BYTES`;
repeated blank lines can hide a dropped empty line; for fills, read the box before sending —
`APPLIED` means the box held the asked content at the re-read after pending microtasks plus
one settle interval (250 ms in this build); `settle_interval_ms` is a floor, not a ceiling
(hidden tabs settle later — do not timeout-and-retry a fill that may have applied).

## Operator call: stepped menu choice (new in BR2)

`menu` chooses an item in a stepped menu by ref (items 1/2). After `snapshot` gives
the opener `ref`:

```json
{"action":"menu","browser_id":"<browsers>","connection_id":"<status>",
 "tab_id":0,"url_fingerprint":"<tabs>","snapshot_id":"<snapshot>","ref":"<opener ref>",
 "labels":["Thinking","Extra High"]}
```

`labels` is 1–3 item labels, one per menu step (a single label for a flat menu, two
for a submenu such as Thinking → Extra High). The page world opens the opener, walks
the labels, clicks the final item and reads the value back. The receipt is `APPLIED`
only with read-back evidence (item-state → opener-text → reopen-item-state); an
unreadable value is `EFFECT_UNKNOWN` with `read_back:null` and the act is never
repeated. Refusals are typed (`MENU_ITEM_NOT_FOUND`, `MENU_AMBIGUOUS`,
`MENU_NOT_OPENED`, `TARGET_DISABLED`, `INPUT_REFUSED`) and disclose `menu_left_open`.
Bounded: ≤60 items, 4000 ms. `menu` exists only on a new-pin session whose profile
has been reloaded (window table above); an old-pin session receives
`ACTION_UNAVAILABLE`.

## Rollback target

`b640dec1461a29cd5e42910c992973f50597d93f` — its release directory is never modified
by any step; step 4's repoint back plus step 3's reload from the untouched
`0.6.0-b640dec1` folders returns every profile and session to it. Lane BR2 wrote
nothing under `~/.local/share/mastermind-browser-control`, `~/.t3`,
`~/Library/Application Support/Google/Chrome`, any Chrome folder, `~/Downloads` or
any provider home; every step above is the principal's.