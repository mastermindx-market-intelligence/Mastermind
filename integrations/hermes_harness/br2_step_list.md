# BR2 install step list — bridge release after b640dec1 (STAGED; install is the principal's)

Branch `t3/mmos-v4-br2`. Staged base **`NEW = 920544c6bc98f5bfd403ad7baf73968ec1d89935`**;
base trunk `473eca8cf` (bridge bytes identical to b640dec1). This step list's own
commits sit atop `NEW`: the install re-curates step 1's manifest at the branch head
and the installed `release_commit` is that head, not `920544c6b`. The transport
compatibility constants are identical at `NEW` and the branch head because no commit
atop `NEW` touches protocol source or the 15-file server closure (the review fixes
are in the extension's `browser_control.js`, `runtime_pin.py`, a comment, and these
documents). The ruling-16 rehearsal below was run against
`1a4fa86765b20329d9c0ababbd66c152dd3f5a6f` (the branch head after the review source
fixes), whose closure is byte-identical to `NEW`. Method mirrored from the proven
release-3 runbook (`integrations/hermes_harness/mcp_bridge_install.md`, rehearsal
`~/.mastermind/mmos_dev/br/compat/drivers/switch_rehearsal.py`). Mirrored at
`~/.mastermind/mmos_evidence/br2-20261114/STEP_LIST.md`.

- **OLD (rollback / admitted previous)** = `b640dec1461a29cd5e42910c992973f50597d93f`
  — 41 browser actions, digest
  `1c40ec98d1086a8f8005151757b040698057019f5e9169cace91e393b6f60d40` (`read` present, `menu` absent).
- **NEW (this release)** = `920544c6bc98f5bfd403ad7baf73968ec1d89935`
  — 42 browser actions, digest
  `08c66c330c9d3cd6728ff67628aa314afd446389b6bd394a93a9f8b63672a05a` (`menu` added).
- Delta is exactly **+`menu`**. `WEB_SOL_PACKAGE_VERSION` stays `0.4.0`, extension
  manifest version stays `0.4.1`; only the digest moves. The MCP enum is the
  browser set **plus 3 local actions** (`browsers`, `hosts`, `launch`): OLD 44, NEW 45.

BR2 adds the stepped `menu` action (item 1/2), the orphan-tab `close` guard
(item 3), and snapshot `ensure_role`/`ensure_name` (item 4). The compat admission
(`PREVIOUS_TRANSPORT_CAPABILITY_DIGEST = 1c40ec98…`, commit b640dec1) lets the NEW
host admit the OLD release's digest and hold that connection to the 41 old
actions; `menu` exists only where both ends describe it.

---

## 0. Install-sequencing context the principal must read first (live state)

Verified this session against the live machine (read-only):

- The **live flat pin is still `5aa30969241163b4abb3e025bc9e52123ee4b478`**
  (`~/.t3/mcp/mmx-browser/runtime.json` `release_commit`), 40 actions, digest
  `e0216d3d9e9f05edef32ff642cb82a1281b1a9766d5cc35f694c88e0ef0bb0bb`.
- **b640dec1 is installed-but-NOT-switched**: its release root exists and its
  install step 2 ran (`br-install-20261112b/RESULT.md`), but the pin switch and
  the Chairman's five extension reloads are still pending. The loaded extension
  folders are still the `0.4.0` renders (digest `e0216d3d…`).
- **BR2's compat window admits exactly b640dec1 (`1c40ec98…`), NOT `e0216d3d…`.**
  Ruling 17 fixes the admitted previous to one named release. Consequences:
  - A BR2 host **refuses** a peer presenting `e0216d3d…` (today's loaded `0.4.0`
    extension and today's live-pin client). A BR2 extension (`08c66c33…`) is
    **refused** by a b640dec1 host (which admits `1c40ec98…` + `e0216d3d…`).
  - Therefore BR2 **cannot** be switched in directly over the current
    `5aa30969`/`0.4.0` fleet without a breakage window: the not-yet-reloaded
    `0.4.0` profiles would meet a BR2 host that does not admit their digest.

**Safe sequencing (principal's decision):** complete b640dec1's sitting first —
the five reloads to the b640dec1 extension (`1c40ec98…`) and the pin switch to
b640dec1 — so the whole fleet is uniformly on b640dec1, **then** run the BR2
steps below over b640dec1 (its admitted previous). The brief's "one reload
sitting instead of two" goal is only safe if the principal coordinates the two
releases so that no `e0216d3d…` peer ever meets a BR2 host and no `08c66c33…`
extension ever meets a b640dec1 host; the window table below is proven for the
**b640dec1 → BR2** hop, which is the hop BR2's admission covers. This is surfaced,
not decided, here: install and pin switch are the principal's.

---

## 1. Per item: extension change (Chairman Load unpacked) vs server-only

| Item | What changes | Reload needed? |
|---|---|---|
| 1 — stepped menu by ref | `browser_page.js` menu walker + `browser_control.js` route (extension) **and** `web_sol_browser_protocol.py`/`browser_tool_schema.json`/`web_sol_protocol.py` (server) | **Yes** — extension bytes change; Chairman must remove + Load unpacked per profile |
| 2 — model-menu item | Same mechanism as item 1 (menuitemradio shape); no separate code | Covered by item 1's reload |
| 3 — orphan-tab close | `browser_control.js` opener-record durability via `chrome.storage.session` (extension) + manifest `storage` permission + host/protocol typed codes (server) | **Yes** — extension bytes + manifest permission change |
| 4 — composer past cap | `browser_page.js` snapshot `ensure_role`/`ensure_name` (extension) + protocol/schema (server) | **Yes** — extension bytes change |
| LOW1/LOW2, delivery lock | server-side only (`_web_sol_native_host_impl.py`, `web_sol_protocol.py`, `runtime_pin.py`) | No (host respawn picks them up) |

All four items change the extension, so the Chairman's remove + Load unpacked
sitting is required for the new abilities; the server-only fold-ins land on host
respawn. The digest move (`08c66c33…`) is what makes the reload necessary.

---

## 2. Install steps (principal's; order matters — build, reload, switch the pin LAST)

`BASE=~/.local/share/mastermind-browser-control`,
`STAGING=~/Downloads/Mastermind-Browser-0.6.0-920544c6b` (fresh per-release root,
never a folder any Chrome has loaded), `MMX=~/.t3/mcp/mmx-browser`. The guarded
commands (`install_browser`, `runtime_pin migrate/switch`,
`mmx_provider_registration`) are unchanged from release 3; only the constants
below move. Every step has a rollback (§4). Full prose in
`integrations/hermes_harness/mcp_bridge_install.md`.

1. **Stage the tree + curate the build manifest** at `$NEW`. Check
   `git rev-parse HEAD` = `$NEW` (or the branch head whose transport constants
   match) and these runtime hashes (recomputed at head):
   - `web_sol_browser_protocol.py` = `755c094955b08c97d54b2bce89c88e9e33e42ecc61247c33cb01b25f2319e824`
   - `web_sol_protocol.py` = `a37ae64b8f649b1b9bbd02673de4dba16bee1b5d04fb2b5fe8ad084b267c984b`
   - `browser_bridge.py` = `f1d78a60343c113ea01fef399ec93cd0b6da461c7b944bf932524cc4f4788d18`
   - `browser_tool_schema.json` = `c34bf7a30383a6eab3079259e6d9333d4dc8be179565b7a104d86860308cdf55`
   - `background.js` pins `EXPECTED_CAPABILITY_DIGEST = "08c66c33…b63672a05a"`
     (file sha256 `4ce652acd500852a7b8d71dbeed910089e0f3350044f54847785374b2f5deb05`).
   Curate `BUILD-920544c6b.json` from the b640dec1 `BUILD.json` (keep existing
   paths re-hashed at `$NEW`, drop gone paths — none at this head — add the new
   BR2 tests `browser_menu_playwright.cjs`, `browser_snapshot_ensure_playwright.cjs`,
   `browser_orphan_close_contract.cjs`, `test_web_sol_browser_menu_ensure.py`,
   `test_web_sol_transport_gates.py`). Schema string exactly
   `mastermind.browser_direct_build.v1`. Check: **70 files** (65 kept from
   b640dec1 + 5 new).
2. **Build the release + register hosts** (`install_browser --build-manifest
   BUILD-920544c6b.json --staging-root $STAGING --prior-source b640dec1…`,
   default `update_loaded=False`). From this moment any host respawn runs BR2
   host code — safe at every moment below **over a b640dec1 fleet** because the
   BR2 host admits `1c40ec98…`. Check: `state=INSTALLED_PENDING_CHROME_LOAD`,
   loaded `0.6.0-b640dec1` folders byte-identical,
   `STAGING/Chrome-<alias>/instance_config.js` carries digest `08c66c33…`,
   manifest permissions include `storage`.
3. **Operator extension reloads, profile by profile** (human action; ⟳ alone is
   not enough — it re-reads the old loaded folder). Remove the extension, Load
   unpacked from `STAGING/Chrome-<alias>`. The manifest `key` keeps the id and
   `allowed_origins` unchanged. **True remove+load statement (item 3):** BR2 adds
   `chrome.storage.session` for opener-record durability (`mmxOpenerRecords`) and
   the activity ledger; remove+load **clears** that session storage, so a tab the
   bridge opened before the reload then refuses close with `TAB_NOT_BRIDGE_OPENED`
   (fail-closed) and must be closed by hand. Records rebuild on the next open; no
   operator or live-session tab ever becomes closable by this loss. One profile at
   a time, confirming the previous still answers. Do all five.
4. **Switch the pin — LAST** (`runtime_pin migrate` then
   `mmx_provider_registration` then `runtime_pin switch --commit $NEW`). Never
   hand-edit the flat pin or `.claude.json`. Check: fresh session
   `bridge_release_commit` `$NEW`, enum 45 incl `menu`; old sessions keep
   answering `b640dec1…` (rehearsed below).
5. **Verify in a fresh session** (read-only): `browsers probe:true` five profiles
   `CONNECTED` on `$NEW`; enum 45 incl `menu`; one old session still answers
   on `b640dec1…` with `menu` absent (correct for its pin).

---

## 3. Ruling-17 window table (every cell works; `menu` only where both ends describe it)

"Old-pin session" = server resolved `current` before step 4's repoint (b640dec1
pin, `1c40ec98…`, 41 actions). "New-pin session" = server spawned after it
(BR2 pin, `08c66c33…`, 42 actions). "Reloaded profile" = BR2 extension
(`08c66c33…`) + BR2 host. "Not-yet-reloaded" = b640dec1 extension (`1c40ec98…`)
+ host (b640dec1 alive, or BR2 on respawn — both admit `1c40ec98…`). `menu`
absent means: all 41 old actions work; the `menu` action does not exist for that
session (it never asks for it). **This table is for the b640dec1 → BR2 hop**
(see §0 for why the fleet must be on b640dec1 first).

| Moment | Session pin | Reloaded profile (BR2 ext) | Not-yet-reloaded (b640dec1 ext) |
|---|---|---|---|
| after step 2 (build+register) | old | — | works; host b640dec1 alive or BR2 on respawn, either admits `1c40ec98…`; `menu` absent |
| during step 3, per profile done | old | works (BR2 ext + BR2 host; old b640dec1 client admitted on previous digest `1c40ec98…`); `menu` absent | works as the row above |
| after step 3, before step 4 | old | works; `menu` absent | none left — step 3 does all five |
| after step 4 repoint | old | works, unchanged; `menu` absent | none (by the step-3 gate) |
| after step 4 repoint | new | works; `menu` admitted and executed | none (by the step-3 gate) |
| step 5 verify | old / new | works / works + `menu` | none |

Two invariants make the empty cells structural: (a) the pin switch is last, so
no new-pin session exists while any profile is still on the b640dec1 extension;
(b) step 3 completes every profile before step 4, so no new client meets a live
old-code host. **The person-performed step (3, reload) comes before the step
that makes new sessions depend on it (4, pin switch)** — ruling 17 satisfied.
A session spawned at any moment resolves the pin `current` held at its spawn.

---

## 4. Rollback window (reverse step order; OLD release + old loaded folders never modified)

| Step | What is live | How to undo | Until when |
|---|---|---|---|
| 1 | Nothing runtime-side; only curated `BUILD-920544c6b.json` in the checkout. | Delete the manifest; `git checkout` back. | Until step 2 consumes it. |
| 2 | New release root; host manifests point into `releases/$NEW` (BR2 host admits `1c40ec98…`); loaded folders byte-identical; running sessions unchanged. | Restore every `.previous.<16hex>` backup under `BASE` and Chrome `NativeMessagingHosts` (incl `deployments-v2.json`), delete new-only `releases/$NEW/`, `installation-$NEW.json`, `packages/$NEW/`, `$STAGING/`. | Only while no profile reloaded at step 3; after any reload, undo step 3 first (reverse reload to the untouched b640dec1 folders). |
| 3 | Per reloaded profile: BR2 extension + BR2 host; answers old-pin and new-pin alike (compat admission). | Reverse reload: remove + Load unpacked from the untouched `~/Downloads/Mastermind-Browser-0.6.0-b640dec1/Chrome-<alias>` folder. | Any later point (BR2 host admits b640dec1 digest); in a full rollback do it after undoing step 4. |
| 4 | New spawns resolve `current`→`runtimes/$NEW` (`menu` present); running sessions keep their resolved b640dec1 files. | `runtime_pin switch --mmx-root $MMX --commit b640dec1…` (one atomic repoint). To undo the whole migration, restore the four `.claude.json.previous.<16hex>` backups and LEAVE `runtimes/`+`current` in place. | Until the NEXT release replaces the compat window (it admits only one previous digest); then b640dec1 is no longer a rollback target. |
| 5 | Everything reloaded/switched; old sessions draining. | Read-only; on failed check roll back 4→3→2. | End of sitting. |

**Undo whole-tree comparison (ruling 16):** the rehearsal (§5) hashed the real
`~/.t3/mcp/mmx-browser` pin folder before and after — **zero difference**. Lane
BR2 wrote nothing under `~/.local/share/mastermind-browser-control`, `~/.t3`,
`~/Library/Application Support/Google/Chrome`, any Chrome folder, `~/Downloads`,
or any provider home; every install step above is the principal's. The OLD
(b640dec1) release directory and the old loaded folders are never modified by
any step, so the bytes every undo needs always exist.

---

## 5. Ruling-16 rehearsal — output (scratch `~/.mastermind/mmos_dev/br2/rehearsal/`)

Method: `~/.mastermind/mmos_dev/br2/rehearsal_switch.py`, mirroring the proven
`br/compat/drivers/switch_rehearsal.py` (fresh_call.py + brcompat method), re-run
against the new head `1a4fa86765b20329d9c0ababbd66c152dd3f5a6f` (closure
byte-identical to `NEW`). Both 15-file source closures extracted with `git show`
into scratch (all bridge imports stay inside the closure); `runtime.json` per
release points only at scratch paths; bindings is an empty valid v2 inventory
(no real profiles, no real connections); `server.js` byte-identical copies;
atomic `current` repoint via `os.replace`. **No transport probe (`probe:true`)
anywhere.** Read-only `browsers` + `status` only. Driver log:

```
runtimes prepared; current -> b640dec14
[1] start A via current/ (-> OLD pin b640dec1)
    A actions=44 read=True menu=False
    A commit=b640dec1461a
[2] repoint current -> NEW (atomic); probe the SAME running server A
    current -> 1a4fa8676
    A actions=44 read=True menu=False commit=b640dec1461a
    OLD SESSION KEEPS WORKING (menu still absent on the running old session)
[3] start B via current/ (-> NEW pin 1a4fa8676)
    B actions=45 read=True menu=True commit=1a4fa86765b2
[undo] real MMX pin folder before==after: ZERO DIFFERENCE (rehearsal wrote only scratch)
SWITCH REHEARSAL PASSED
```

(enum 44 = 41 browser + 3 local; 45 = 42 + 3. Server stderr: only
`mmx-browser-mcp: ready (release b640dec1461a…)` and `…(release 1a4fa86765b2…)`.
Full log: `rehearsal/logs/rehearsal_switch.log`; before/after pin trees:
`rehearsal/logs/mmx-before.txt` = `mmx-after.txt`, verified identical.)

What this proves: a running b640dec1 server keeps its commit and action set
across the atomic repoint (no running session disturbed); the next server
resolves BR2 (`menu` present); the real pin folder is untouched. What it does
**not** prove: the operator reload journey (step 3) and step 5's five-profile
`CONNECTED` — no Chrome runs on the scratch instance ids; those are the
operator's on the real machine. The transport rows they rely on are proven at
protocol level by the pytest suites (§6).

---

## 6. Proof inventory (what is proven, and how)

- **Fixture DOM proofs (isolated headless Chromium, ephemeral contexts, no real
  profile/port/extension-load), at head — all PASS:**
  - `tests/browser_menu_playwright.cjs` (items 1+2): menuitemradio model menu
    (the ChatGPT model-menu shape), close-on-choice opener-text read-back, open
    item-state read-back, reopen-only read-back, **unreadable → EFFECT_UNKNOWN
    never repeated**, two-step submenu (Effort→Extra High), popover listbox
    aria-selected, typed MENU_ITEM_NOT_FOUND/MENU_AMBIGUOUS/MENU_NOT_OPENED/
    TARGET_DISABLED/INPUT_REFUSED, one-snapshot-one-operation, offscreen opener
    refused without scrolling. Log: `logs/green-menu.txt`.
  - `tests/browser_snapshot_ensure_playwright.cjs` (item 4): composer past the
    120-element cap gets a reachable ref via `ensure_role`; no scroll/focus/DOM
    change; fill works offscreen through the ref; click keeps TARGET_OFFSCREEN;
    ensure_name hit/typed miss; role already in cap reports existing ref.
    Log: `logs/green-ensure.txt`.
  - `tests/browser_orphan_close_contract.cjs` (item 3, vm contract + chrome
    storage stub): live opener's tab refused `TAB_OWNER_SESSION_LIVE` stays open;
    operator tab refused `TAB_NOT_BRIDGE_OPENED` stays open; orphan past lease
    closable with `orphan_close` disclosure; records survive a service-worker
    restart; no storage fails closed; onRemoved clears memory+persistence;
    forged close params refused. Log: `logs/green-orphan.txt`.
- **Review round-1 regression cases (fail at 920544c6b, pass with the fix):**
  `tests/browser_control_contract.cjs` MED-1 concurrent-open (one BUSY);
  `tests/test_runtime_pin_guard.py` LOW-1 lock-exit (body exception preserved;
  clean exit tolerates external removal). Logs: `logs/failing-first-med1.txt`,
  `logs/failing-first-low1.txt`, `logs/green-med1.txt`, `logs/green-low1.txt`.
- **Real-pipe transport suites (pytest, real `run_native_host` + extension
  stand-in), green at head:** `test_web_sol_transport_compat.py` 11/11 (old
  client admitted, menu refused without forwarding, old extension holds menu
  back from a new client, third digest refused at handshake),
  `test_web_sol_transport_gates.py` 13/13 (LOW1 census/surface intersection,
  LOW2 digest-swap refusal), `test_web_sol_browser_menu_ensure.py` 28/28.
- **Server-side pin-switch rehearsal:** §5 (PASS, zero-diff, against the new head).
- **Staged bundle (re-staged at the final head, includes the MED-1 fix):**
  `~/.mastermind/mmos_dev/br2/staging/extensions/aaaaaaaaaaaaaaaaaaaaaaaa`
  (13 files), sha256 manifest `~/.mastermind/mmos_dev/br2/staging/extension-sha256.txt`
  (all 13 verify OK), bundle digest
  `10932a1abd9675bbb7b8488947b372a06491397862d836c1fade7bfdf1b51582`,
  `instance_config.js` digest `08c66c33…`, manifest permissions include `storage`.
  The bundle embeds no head commit, so its digest is stable across the doc-only
  commits atop the MED-1 source fix; restage log `logs/restage-finalhead.txt`.

## 7. What is NOT proven (honest)

- **Nothing was tried on a ChatGPT page.** The real ChatGPT Thinking-effort menu
  shape (Pro / Extra High) is unproven; item 1/2 are proven only on the
  menuitemradio fixture of the same shape. Real popover/submenu timing, shadow
  DOM, or React-portal menus on chatgpt.com may differ.
- The full loaded-extension end-to-end (extension service worker → real native
  host → bridge) on a real profile is not separately exercised here; the page
  world is proven by injection fixtures, the host/bridge by real-pipe pytest and
  the vm contract, and the pin switch by the scratch rehearsal. The operator's
  step-3 reload + step-5 `CONNECTED` proof remain the principal's on the real
  machine.
- The b640dec1 → BR2 window table is proven for that hop only; the live fleet is
  still on `5aa30969`/`0.4.0` (§0), so the principal must sequence b640dec1's
  sitting first. A direct `0.4.0` → BR2 jump is **not** covered by BR2's
  single-previous admission and would break not-yet-reloaded profiles.
- Pre-existing base failures (not introduced by BR2) are catalogued in
  `PREEXISTING_FAILURES.md`; BR2 introduces zero new failures and fixes one
  base-failing reconstitution manifest test.