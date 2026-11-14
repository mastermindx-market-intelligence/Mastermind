# BR2 install step list — the single hop 5aa30969 → BR2 (RULING BR2-R2; install is the principal's)

Branch `t3/mmos-v4-br2`. **Staged head `NEW = bcde4466e36cbfe3b8a0e704a1e509e7852fee10`**
(on origin; one commit on `faa974f32`). This list supersedes the earlier
b640dec1 → BR2 list: the accepted previous release is now the one **actually live at
both ends**, so the Chairman reloads the five profiles **once**, straight from the
0.4.0 renders to BR2. b640dec1 is a **skipped** release — its digest is admitted
nowhere by BR2. Method mirrored from the proven release-3 runbook
(`integrations/hermes_harness/mcp_bridge_install.md`). Mirrored identically at
`~/.mastermind/mmos_evidence/br2-20261114/STEP_LIST.md`.

## Constants (one constant pair; every other digest is refused)

| Role | Commit | Capability digest | Browser actions | MCP enum |
|---|---|---|---|---|
| **OLD** = admitted previous / rollback | `5aa30969241163b4abb3e025bc9e52123ee4b478` | `e0216d3d9e9f05edef32ff642cb82a1281b1a9766d5cc35f694c88e0ef0bb0bb` | 40 (`read` absent, `menu` absent) | 43 |
| **SKIPPED** (admitted nowhere) | `b640dec1461a29cd5e42910c992973f50597d93f` | `1c40ec98d1086a8f8005151757b040698057019f5e9169cace91e393b6f60d40` | 41 | 44 |
| **NEW** = BR2 (this release) | `bcde4466e36cbfe3b8a0e704a1e509e7852fee10` | `08c66c330c9d3cd6728ff67628aa314afd446389b6bd394a93a9f8b63672a05a` | 42 (`read` + `menu`) | 45 |

- Delta OLD → NEW is exactly **+`read` +`menu`**. The previous surface = the current
  surface minus `read` and `menu` (`web_sol_browser_protocol.py` `PREVIOUS_ACTIONS`,
  40 actions; `web_sol_protocol.py:317` `PREVIOUS_TRANSPORT_CAPABILITY_RELEASE_COMMIT
  = 5aa30969…`, `:320` `…DIGEST = e0216d3d…`).
- MCP enum = browser set **+ 3 local actions** (`browsers`, `hosts`, `launch`,
  `browser_bridge.py:30`): OLD 43, NEW 45.
- `WEB_SOL_PACKAGE_VERSION` stays `0.4.0`; extension manifest version stays `0.4.1`;
  only the digest moves. `background.js:23` pins
  `EXPECTED_CAPABILITY_DIGEST = "08c66c33…b63672a05a"`.
- The host admits exactly its own digest (`08c66c33…`) **plus one previous**
  (`e0216d3d…`); `1c40ec98…` is refused at the handshake (rehearsal leg L4).

---

## 0. Real starting state (read-only census; `logs/real-state-read-only.txt`)

- **Live flat pin = `5aa30969…`** (`~/.t3/mcp/mmx-browser/runtime.json`
  `release_commit`). Pin folder is exactly `{README.md, runtime.json, server.js}` —
  **no `runtimes/`, no `current`**; `runtime_pin migrate` has never run.
- **Six user-level Chrome `NativeMessagingHosts` manifests**
  (`com.mastermind.web_sol_surface.<id24>.json`, + `.previous` backups) all point
  into the **b640dec1** release's per-profile `bin/` wrappers (b640dec1's install
  step 2 ran; b640dec1 never went live as a pin or a loaded extension).
- **Five distinct loaded extension folders**, every one a 0.4.0 render with
  `EXPECTED_CAPABILITY_DIGEST = e0216d3d…` (40 actions):
  - Default (personal-default) → `~/Downloads/Mastermind-Browser-0.4.0/Chrome-Default`
  - Profile 12 (mastermindx) → `~/Downloads/Mastermind-Browser-0.4.0/Chrome-Default`
    (same folder; pre-existing `PROFILE_IDENTITY_MISMATCH`, unrelated to this release)
  - Profile 17 (chatgpt1) → `~/Downloads/Mastermind-Browser-0.5.0/Chrome-chatgpt1`
  - Profile 18 (chatgpt2) → `~/Downloads/Mastermind-Browser-0.5.0/Chrome-chatgpt2`
  - Profile 19 (chatgpt3) → `~/Downloads/Mastermind-Browser-0.5.0/Chrome-chatgpt3`
  - Profile 20 (chatgpt4) → `~/Downloads/Mastermind-Browser-0.4.0/Chrome-ChatGPT4`
- **Remote hosts** (`deployments-v2.json`): `mini1`, `ubuntu4` each run the
  `5aa30969…` release on their **own** pin (`manifest_sha256 0674c854…`), extension
  0.5.0 render. See §6.

**Why this hop is safe directly over the live fleet (no b640dec1 sitting first):**
BR2's admitted previous is `e0216d3d…` — exactly the digest the five loaded 0.4.0
extensions and the live-pin clients present today. So a BR2 host **admits** the
not-yet-reloaded 0.4.0 extension (rehearsal [2]/L1/L2), and a rolled-back b640dec1
host also admits `e0216d3d…` (b640dec1's own previous = 5aa30969; census line 39-42).
The earlier "complete b640dec1 first" sequencing is **obsolete**: it was needed only
when BR2's previous was `1c40ec98…`. `read`/`menu` still require both ends to describe
them, so they appear only after a profile is reloaded to BR2 **and** its session is on
the new pin (§3).

---

## 1. Per item: extension change (Chairman remove + Load unpacked) vs server-only

| Item | What changes | Reload needed? |
|---|---|---|
| stepped `menu` by ref (+ model-menu item) | `browser_page.js` menu walker + `browser_control.js` route (extension) **and** `web_sol_browser_protocol.py` / `browser_tool_schema.json` / `web_sol_protocol.py` (server) | **Yes** — extension bytes change |
| `read` action | extension page reader + server protocol/schema | **Yes** — extension bytes change |
| orphan-tab `close` guard + 90-min lease + `opened_at` fallback (CHANGE 2) | `browser_control.js` opener-record durability via `chrome.storage.session` (extension) + host/protocol typed codes (server) | **Yes** — extension bytes + manifest `storage` permission |
| snapshot `ensure_role` / `ensure_name` | `browser_page.js` (extension) + protocol/schema (server) | **Yes** — extension bytes change |
| delivery lock / pin writer / compat admission | server-side only (`_web_sol_native_host_impl.py`, `web_sol_protocol.py`, `runtime_pin.py`) | No — host respawn picks them up |

The digest move (`08c66c33…`) is what makes the reload necessary. The server-only
fold-ins land on host respawn.

---

## 2. Install steps (principal's; order matters — build, reload, switch the pin LAST)

`BASE=~/.local/share/mastermind-browser-control`,
`STAGING=~/Downloads/Mastermind-Browser-0.6.0-bcde4466e` (fresh per-release root the
principal creates; never a folder any Chrome has loaded),
`MMX=~/.t3/mcp/mmx-browser`. The guarded CLIs are run from the repo root checked out
at `$NEW`, as modules, with the explicit interpreter
`/opt/homebrew/bin/python3.12` (the interpreter the rehearsal used). The **host
runtime** python passed to `install_browser --python` is the pinned
`~/.hermes/tools/python-3.14.9+20261021-darwin-arm64/bin/python3.14` — a different
interpreter from the installer CLI. Every step has a rollback (§5).

1. **Stage the tree + curate the build manifest** at `$NEW`. Check
   `git rev-parse HEAD` = `$NEW` and `background.js` pins
   `EXPECTED_CAPABILITY_DIGEST = "08c66c33…b63672a05a"`. Curate
   `BUILD-bcde4466e.json` from the b640dec1 `BUILD.json` (keep existing paths
   re-hashed at `$NEW`, drop gone paths, add the BR2/R2 tests:
   `tests/browser_menu_playwright.cjs`, `tests/browser_snapshot_ensure_playwright.cjs`,
   `tests/browser_orphan_close_contract.cjs`, `tests/test_web_sol_browser_menu_ensure.py`,
   `tests/test_web_sol_transport_gates.py`, `tests/browser_close_lease_r2_contract.cjs`).
   Schema string exactly `mastermind.browser_direct_build.v1`; filename
   `BUILD-bcde4466e.json` (step 2 reads that exact name). Verify the file count and
   the changed runtime hashes at curation time. Rollback: delete the manifest,
   `git checkout` back.
2. **Build the release + register the hosts — THE RE-POINT MOMENT (§4).**
   ```bash
   /opt/homebrew/bin/python3.12 -m integrations.hermes_harness.install_browser \
     --build-manifest BUILD-bcde4466e.json \
     --install-base ~/.local/share/mastermind-browser-control \
     --python ~/.hermes/tools/python-3.14.9+20261021-darwin-arm64/bin/python3.14 \
     --enrollment ~/.mastermind/mmos_evidence/br-20261111/release2/enrollment.json \
     --staging-root ~/Downloads/Mastermind-Browser-0.6.0-bcde4466e \
     --prior-source b640dec1461a29cd5e42910c992973f50597d93f
   ```
   `--prior-source` is **b640dec1** because that is where the six manifests point
   today (the installer backs up and re-points from the prior source). Default
   `update_loaded=False` never rewrites a loaded folder. Check: stdout
   `state=INSTALLED_PENDING_CHROME_LOAD`, `source_commit=$NEW`, all six `chrome[]`
   rows `ok:true`, every loaded row `activation:CHROME_RELOAD_REQUIRED`; the five
   loaded 0.4.0 folders byte-identical before/after; `STAGING/Chrome-<alias>/instance_config.js`
   carries digest `08c66c33…`; manifest permissions include `storage`.
3. **Operator extension reloads, profile by profile** (human action; ⟳ alone re-reads
   the old loaded folder and is not enough). Remove the extension, Load unpacked from
   `STAGING/Chrome-<alias>`. The manifest `key` keeps the id and `allowed_origins`
   unchanged. Remove+load **clears `chrome.storage.session`** (opener records +
   activity ledger): a tab the bridge opened before the reload then refuses close with
   `TAB_NOT_BRIDGE_OPENED` (fail-closed) and must be closed by hand; records rebuild on
   the next open. One profile at a time, confirming the previous still answers. Do all
   five. The loaded version string stays `0.4.1`; the observable change is `read`+`menu`.
4. **Switch the pin — LAST** (the only behavior-changing act). Never hand-edit the flat
   pin or `.claude.json`.
   ```bash
   MMX=~/.t3/mcp/mmx-browser
   OLD=5aa30969241163b4abb3e025bc9e52123ee4b478
   NEW=bcde4466e36cbfe3b8a0e704a1e509e7852fee10
   # (a) one-time migration to versioned runtimes; current ends on OLD, zero behavior change
   /opt/homebrew/bin/python3.12 -m integrations.hermes_harness.runtime_pin migrate \
     --mmx-root $MMX --old-commit $OLD --new-commit $NEW \
     --build-manifest BUILD-bcde4466e.json \
     --new-source-root ~/.local/share/mastermind-browser-control/releases/$NEW
   # (b) register the four provider homes flat -> current/server.js (FLAT CLI, no subcommand)
   /opt/homebrew/bin/python3.12 -m integrations.hermes_harness.mmx_provider_registration \
     --providers-root ~/.t3/providers --mmx-root $MMX
   # (c) atomic repoint current -> NEW
   /opt/homebrew/bin/python3.12 -m integrations.hermes_harness.runtime_pin switch \
     --mmx-root $MMX --commit $NEW
   ```
   Check: `PIN_MIGRATED` then `readlink $MMX/current` ends `/runtimes/$OLD`, flat pin
   bytes unchanged; `PROVIDER_ARGS_SWITCHED` (four homes `SWITCHED`, worker
   `fabric-unified-router-worker` untouched, one `.claude.json.previous.<16hex>` backup
   each); `PIN_SWITCHED`, fresh session `bridge_release_commit=$NEW`, enum 45 incl
   `read`+`menu`; old sessions keep answering `5aa30969…` (rehearsal [5]).
5. **Verify in a fresh session** (read-only): `browsers probe:true` five profiles
   `CONNECTED` on `$NEW`; enum 45 incl `read`+`menu`; one old session still answers on
   `5aa30969…` with `read`/`menu` absent (correct for its pin).

---

## 3. (a) Ruling-17 window table — hop 5aa30969 → BR2

"Old-pin session" = server resolved the flat `5aa30969` pin before step 4(c)
(`e0216d3d…`, 40 browser actions, enum 43). "New-pin session" = server spawned after
step 4(c) (BR2, `08c66c33…`, 42 actions, enum 45). "Reloaded profile" = BR2 extension
(`08c66c33…`) + BR2 host. "Not-yet-reloaded" = 0.4.0 extension (`e0216d3d…`, 40
actions) + host (b640dec1 alive today, or BR2 on respawn after step 2 — **both admit
`e0216d3d…`**). Every cell **works** for the 40 common actions; `read`/`menu` are
absent wherever either end is still on `e0216d3d…`.

| Moment | Session pin | Reloaded profile (BR2 ext) | Not-yet-reloaded (0.4.0 ext) |
|---|---|---|---|
| after step 2 (host re-point) | old | — (none reloaded yet) | works; host b640dec1 alive or BR2 on respawn, either admits `e0216d3d…`; `read`/`menu` absent |
| during step 3, per profile done | old | works; BR2 host admits the old client on previous digest `e0216d3d…`, intersection = client 40 ∩ ext 42 = 40; `read`/`menu` absent (client side) | works as the row above |
| after step 3, before step 4 | old | works; `read`/`menu` absent (old client) | none left — step 3 does all five |
| after step 4(c) repoint | old | works, unchanged; `read`/`menu` absent | none (by the step-3 gate) |
| after step 4(c) repoint | new | works; `read`+`menu` admitted and executed (both ends `08c66c33…`) | none (by the step-3 gate) |
| step 5 verify | old / new | works / works + `read`+`menu` | none |

**What an old-pin session gets if it asks for `read` or `menu` (it must not get them):**
- Its **own bridge** refuses at the argument gate: `browser_bridge.py:146`
  (`arguments["action"] not in protocol.ACTIONS | LOCAL_ACTIONS`, the 5aa30969 40+3
  set) → `INVALID_ARGUMENTS`, never forwarded. The enum it advertises is
  `browser_bridge.py:64` = 43 (no `read`/`menu`).
- Even a hand-built request that reaches a **BR2 host** with an old client digest is
  held at the intersection: `_web_sol_native_host_impl.py:958-977` returns
  `status="ACTION_UNAVAILABLE"`, `effect="NOT_APPLIED"`,
  `data.reason="transport_capability_mismatch"` **before** anything reaches Chrome.
- The **OLD host itself** (5aa30969) does not describe `read`/`menu`:
  `web_sol_browser_protocol.py:102` (`value["action"] in ACTIONS`) fails
  `validate_window` and the host closes the connection typed (rehearsal L0b:
  `frame_header_missing`). Its handshake admission is
  `_web_sol_native_host_impl.py:339` (`_accepted_peer_hello`).

Two invariants make the empty cells structural: (a) the pin switch is **last**, so no
new-pin session exists while any profile is still on the 0.4.0 extension; (b) step 3
completes every profile before step 4, so no new client meets a live old-code host.
**The person-performed step (3, reload) comes before the step that makes new sessions
depend on it (4, pin switch)** — ruling 17 satisfied. `read`/`menu` execute only when
**both** the session's client digest and the extension digest are `08c66c33…`.

---

## 4. (b) The host re-point moment (step 2)

At step 2 the installer backs up and re-points all six `NativeMessagingHosts`
manifests from `releases/b640dec1…/chrome/Profile-*/bin/…` into `releases/$NEW/…`.

- **A running 0.4.0 profile / a running session sees nothing at that instant.** A
  running native host already resolved its wrapper and code; it keeps serving on its
  open channel. Rehearsal [2]: a running b640dec1 host still answers `status` after
  the manifest is re-pointed.
- **On the next host respawn** (Chrome re-reads the manifest after the extension
  removal at step 3, or a fresh spawn), the host is **BR2 code**. The BR2 host admits
  the 0.4.0 extension digest `e0216d3d…` (previous), so a not-yet-reloaded profile
  keeps working: rehearsal [2] L1 (old client) and L2 (new client) both `status OK`,
  `read`/`menu` `ACTION_UNAVAILABLE`, and **nothing but `status` ever reached the 0.4.0
  extension**. The loaded extension folders are byte-identical across step 2
  (`update_loaded=False`).

---

## 5. (c) Rollback at every step (reverse order; OLD release + 0.4.0 folders never modified)

| Step | What is live | How to undo | Until when |
|---|---|---|---|
| 1 | Nothing runtime-side; only curated `BUILD-bcde4466e.json` in the checkout. | Delete the manifest; `git checkout` back. | Until step 2 consumes it. |
| 2 | New release root; six host manifests point into `releases/$NEW` (BR2 host admits `e0216d3d…`); loaded folders byte-identical; running sessions unchanged. | Restore every `.previous.<16hex>` backup under `BASE` and Chrome `NativeMessagingHosts` (incl `deployments-v2.json`'s own `.previous`) — manifests go back into **b640dec1**, which admits `e0216d3d…`; delete new-only `releases/$NEW/`, `installation-$NEW.json`, `packages/$NEW/`, `$STAGING/`. | Only while no profile reloaded at step 3; after any reload, undo step 3 first. |
| 3 | Per reloaded profile: BR2 extension + BR2 host; answers old-pin and new-pin alike. | **Reverse reload**: remove + Load unpacked from the untouched 0.4.0 folder (`~/Downloads/Mastermind-Browser-0.4.0/Chrome-Default`, `…0.5.0/Chrome-chatgpt1/2/3`, `…0.4.0/Chrome-ChatGPT4`). Those bytes were never changed by any step. | Any later point; in a full rollback do it after undoing step 4. |
| 4 | New spawns resolve `current`→`runtimes/$NEW` (`read`+`menu`); running sessions keep their resolved 5aa30969 files. | `runtime_pin switch --mmx-root $MMX --commit $OLD` (one atomic repoint). To undo the whole migration, restore the four `.claude.json.previous.<16hex>` backups and **LEAVE `runtimes/`+`current` in place** (ruling 19: a delivery mark is permanent; deleting them breaks servers spawned via `current/server.js`). | Until the NEXT release replaces the compat window (it admits only one previous digest); then 5aa30969 is no longer a rollback target. |
| 5 | Everything reloaded/switched; old sessions draining. | Read-only; on a failed check roll back 4→3→2. | End of sitting. |

**Rollback order constraint (proven, rehearsal L6):** a BR2-loaded profile
(`08c66c33…`) is **inert against a rolled-back b640dec1 host** — b640dec1 admits
`{1c40ec98…, e0216d3d…}`, **not** `08c66c33…`, so the extension handshake is refused
(host exit 65). **A BR2-loaded profile must be reverse-reloaded to its 0.4.0 folder
BEFORE its host is rolled back to b640dec1.** Restoring the b640dec1 host manifests
under a still-BR2 profile breaks that profile.

**Undo whole-tree comparison (ruling 16):** the rehearsal (§8) hashed the real
`~/.t3/mcp/mmx-browser` pin tree (3 files) and all real `NativeMessagingHosts`
(29 files) before and after — **zero difference** — and the scratch whole-tree undo
was zero-difference (9 files; `runtimes/`+`current` remain by design). This lane wrote
nothing under `BASE`, `~/.t3`, any Chrome folder, `~/Downloads`, or any provider home;
every install step above is the principal's. The b640dec1 release directory and the
0.4.0 loaded folders are never modified by any step, so the bytes every undo needs
always exist.

---

## 6. (d) Remote callers through `routes.remote_call` (read-only source finding; no host touched)

Sessions on the Linux hosts reach the M2 bridge through `routes.remote_call`. The
action surface for such a call is decided by **both** releases, as an intersection:

- **M2's release decides whether the action is forwardable.** An ssh-host action is
  forwarded at `browser_bridge.py:214-215` → `forwarded(host)` → `routes.remote_call`
  (`:166`). The forwarding gate `browser_bridge.py:146`
  (`arguments["action"] not in protocol.ACTIONS | LOCAL_ACTIONS`) uses **M2's own
  pinned protocol**. After the hop M2 is BR2 (42), so M2 will forward `read`/`menu`.
- **The remote host's OWN release decides whether it executes.** `remote_call`
  (`browser_routes.py:259-261`) SSHes to the remote and runs `REMOTE_BOOT`
  (`:226-256`) against the remote's **own** `source_root` + `manifest_sha256`: it
  verifies the remote `BUILD.json` sha256 == `manifest_sha256` (`:242`) and every file
  hash (`:245-248`), imports from the remote `source_root` (`:249`), and runs
  `browser_bridge.main(["--bindings",…,"--profile",…,"--local-only"])` (`:255`) — the
  remote's pinned release executes the action locally. `mini1`/`ubuntu4` run
  `5aa30969…` (40 actions), so a forwarded `read`/`menu` is refused **at the remote**.
- **Effective surface = intersection** of M2's forwarding set and the remote's
  execution set. The 40 common actions work throughout.

**No remote pin has to move for the M2 hop**, and **either upgrade order is
refusal-safe**: if M2 upgrades first, `read`/`menu` to a remote profile are refused at
the remote (fail-closed); if a remote upgrades first, an old M2 pin still refuses to
forward `read`/`menu` at `browser_bridge.py:146`. There is no window where an action is
dispatched to an end that does not describe it. Enabling `read`/`menu` on a remote
profile is a **separate remote install** of a release that describes them, on that
host's own pin — not part of this M2 hop. (Finding from source only; no ssh, no host
write.)

---

## 7. (e) Digests, the 13-file manifest, and the expected load folder names

- **Capability digest `08c66c33…` is UNCHANGED this round** (faa974f32 → bcde4466e
  touches `browser_control.js`'s lease constant + `opened_at` fallback, not the
  capability surface). Current = `08c66c330c9d3cd6728ff67628aa314afd446389b6bd394a93a9f8b63672a05a`;
  admitted previous = `e0216d3d9e9f05edef32ff642cb82a1281b1a9766d5cc35f694c88e0ef0bb0bb`.
- **13-file sha256 manifest:**
  `~/.mastermind/mmos_dev/br2/staging/extension-sha256.txt` — re-verified **13/13 OK**
  this round (`logs/manifest-reverify-r2-author.txt`). Two of the 13 files changed
  bytes vs faa974f32 (`background.js`, `browser_control.js`); the manifest is the
  verifier's stable comparison (the bundle digest changes per commit).
- **Reviewed staged folder:**
  `~/.mastermind/mmos_dev/br2/staging/extensions/aaaaaaaaaaaaaaaaaaaaaaaa` (13 files).
  Bundle digest `c3a61dea0012c9867b1d9d5cced865f864eaf03c3b812009e88460379dac2426`
  rendered at `bcde4466e` (`logs/restage-r2b.txt`); `instance_config.js` digest
  `08c66c33…`; manifest permissions include `storage`.
- **Expected load folder names** (the principal creates these from the reviewed staged
  folder; this lane does not). `STAGING=~/Downloads/Mastermind-Browser-0.6.0-bcde4466e`,
  five distinct renders, one per loaded alias:
  - `STAGING/Chrome-Default` (personal-default; mastermindx shares it)
  - `STAGING/Chrome-chatgpt1`
  - `STAGING/Chrome-chatgpt2`
  - `STAGING/Chrome-chatgpt3`
  - `STAGING/Chrome-ChatGPT4`
  The Chairman removes + Load unpacked from each at step 3. The id and
  `allowed_origins` are unchanged (manifest `key`).

---

## 8. Ruling-16 rehearsal — full-hop output (scratch `~/.mastermind/mmos_dev/br2/rehearsal-r2/`)

Driver `~/.mastermind/mmos_dev/br2/rehearsal_r2.py`, run with the list's exact guarded
CLIs (`runtime_pin migrate/switch`, `mmx_provider_registration`) against a scratch copy
that reproduces the REAL start: flat `5aa30969` pin (no `runtimes/`, no `current`), host
manifest into a scratch b640dec1 wrapper, 0.4.0 extension/client stand-ins (digest
`e0216d3d…`). Host subprocesses run the real 15-file closures extracted with `git show`;
the extension reload is simulated by digest swap (the actual reload is the Chairman's
act). **No transport `probe:true` anywhere; read-only `status` + stand-in receipts.**
Log: `logs/rehearsal-r2.txt` (also `rehearsal-r2/logs/rehearsal-r2.txt`).

```
flat pin reproduced: README.md, runtime.json, server.js (layout == real flat pin)
host manifest reproduced (real shape), path -> scratch b640dec1 wrapper
provider homes reproduced: 4 registered into the flat pin; worker has no entry
OLD=5aa309692 SKIPPED(b640dec1)=b640dec14 NEW=bcde4466e

[L0] REAL STARTING STATE: b640dec1 host + 0.4.0 extension + 0.4.0 client
    status OK; read ACTION_UNAVAILABLE (intersection); menu typed connection close (not in b640dec1 ACTIONS)
    forwarded to extension: ['status']
[L0b] OLD 5aa30969 host, same 0.4.0 peers (its own refusal shape)
    read -> {"connection_closed": "NativeHostError: frame_header_missing"}
    menu -> {"connection_closed": "NativeHostError: frame_header_missing"}
[L0c] new-digest client against the OLD host: no PREVIOUS mechanism there
    L0c: handshake REFUSED (NativeHostError)
[2] THE MANIFEST RE-POINT MOMENT (step 2 of the hop)
    manifest path now -> scratch BR2 wrapper; the RUNNING b640dec1 host:
    still serves status on its already-open channel (unaffected)
    next spawn via the manifest = BR2 host; 0.4.0 extension handshake ADMITTED
    L1 old client: status OK; read/menu ACTION_UNAVAILABLE (client set = 40)
    L2 new client: status OK; read/menu ACTION_UNAVAILABLE (extension set = 40)
    nothing but status ever reached the 0.4.0 extension
[L3] BR2 host + BR2 extension + BR2 client (reload simulated by digest swap)
    status/menu/read all forwarded and APPLIED (stand-in receipts)
[L4] skipped b640dec1 digest against the BR2 host
    L4: handshake REFUSED (NativeHostError)
[L6] BR2 extension against a rolled-back b640dec1 host (rollback order)
    extension handshake REFUSED; host exit=65
    => a BR2-loaded profile is inert against a rolled-back host:
       reverse-reload the profile to 0.4.0 BEFORE rolling its host back
[3] runtime_pin migrate (real CLI) — current ends on OLD, zero behavior change
    PIN_MIGRATED; current -> runtimes/5aa309692; flat pin bytes unchanged
    server A via current: enum=43 read=False menu=False commit=5aa309692
[4] mmx_provider_registration switch (real CLI) — four homes, worker untouched
    PROVIDER_ARGS_SWITCHED: 4 homes SWITCHED, backups written, worker home untouched
[5] runtime_pin switch LAST (real CLI) — the only behavior-changing act
    running server A unchanged across the switch: enum=43 read=False menu=False commit=5aa309692
    server B via current: enum=45 read=True menu=True commit=bcde4466e
[6] ROLLBACK rehearsal: switch back to OLD, restore providers, re-point manifest
    server C via current after rollback: enum=43 read=False menu=False commit=5aa309692
    provider .claude.json restored from .previous backups (flat path again)
    manifest back to b640dec1; 0.4.0 extension admitted; status OK
    scratch undo whole-tree comparison: 9 files, ZERO DIFFERENCE
    (runtimes/ + current remain by design — a delivery mark is permanent, ruling 19)
[7] ZERO DIFFERENCE on every real root
    real pin tree (3 files) before == after
    real NativeMessagingHosts (29 files) before == after
    ZERO DIFFERENCE — the rehearsal wrote only scratch

WINDOW-TABLE CITATIONS (file:line)
  old-pin session enum gate: browser_bridge.py:64 (enum = protocol.ACTIONS | LOCAL_ACTIONS)
  old-pin session argument gate: browser_bridge.py:146 (action not in ACTIONS|LOCAL_ACTIONS -> refusal)
  BR2 host intersection refusal: _web_sol_native_host_impl.py:958-977 (ACTION_UNAVAILABLE, then return)
  OLD host action validation: 5aa30969 web_sol_browser_protocol.py:102 (action in ACTIONS)
  OLD host handshake admission: 5aa30969 _web_sol_native_host_impl.py:339 (_accepted_peer_hello)

REHEARSAL R2 PASSED
```

What this proves: the real starting state's refusal shapes (L0/L0b/L0c); the host
re-point leaves running sessions untouched and the next BR2 spawn admits the 0.4.0
extension while holding `read`/`menu` back ([2]/L1/L2); BR2+BR2+BR2 forwards `read`+
`menu` (L3); the skipped digest is refused (L4); the rollback order constraint (L6);
migrate → provider → switch-last with a running old server unchanged across the
repoint and a new server on BR2 ([3]/[4]/[5]); and a zero-difference undo on both the
scratch whole tree and every real root ([6]/[7]).

---

## 9. Proof inventory and what is NOT proven

Proven (accepted base faa974f32..bcde4466e, frozen this round; logs in
`~/.mastermind/mmos_evidence/br2-20261114/logs/`): real-pipe transport compat suite
`test_web_sol_transport_compat.py` 12/12 (`green-r2-*`, `verify-previous-digest.txt`);
close-lease contract `browser_close_lease_r2_contract.cjs` (CHANGE 2: 90-min lease,
`opened_at` fallback, owner-alive/unknown refusals before any `chrome.tabs.remove`);
the full-hop scratch rehearsal (§8, PASS, zero-diff). The 13-file manifest re-verified
13/13 this round.

**NOT proven (honest):**
- **Nothing was tried on a ChatGPT page.** The real ChatGPT menu/read shapes are
  unproven; items are proven only on fixtures of the same shape. Real popover/submenu
  timing, shadow DOM or React-portal menus on chatgpt.com may differ.
- The **operator reload journey (step 3)** and **step 5's five-profile `CONNECTED`**
  are not exercised here — no Chrome runs on the scratch instance ids; those are the
  principal's on the real machine. The transport rows they rely on are proven at
  protocol level (§8 + the compat suite).
- **Remote hosts were not touched** (§6 is a read-only source finding); enabling
  `read`/`menu` on a remote profile is a separate remote install.
- The window table is proven for the **5aa30969 → BR2** hop only.