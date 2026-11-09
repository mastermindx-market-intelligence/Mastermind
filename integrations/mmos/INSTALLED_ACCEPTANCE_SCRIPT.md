# Mastermind OS — installed acceptance script (DONE_WHEN 6/7 preparation)

Owner: Director I2 lane (`t3/installed-acceptance-prep`), Fable COO program.
This is the **exact runbook for the principal/human** to replace the running
`~/Applications/Mastermind OS.app` with the built candidate
(`29a82f779f…` / `mmos-v1-integration-20261109-29a82f77`) and take the
installed-user-path evidence. Everything up to the quit is already prepared
and verified by this lane; steps marked **HUMAN** need the human's hands.

Paths are `~`-redacted. Full paths on m2studio: install target
`~/Applications/Mastermind OS.app`; archive root `~/.mastermind/mmos_bundles/`;
a Mastermind checkout at head `29a82f779` (e.g. the T3 worktree
`~/.t3/worktrees/Mastermind/t3-af983385`). `$R` below is:

```sh
R="env -u PYTHONPATH /opt/homebrew/bin/python3.12 scripts/mmos_rollback.py"
# run from any Mastermind checkout at head 29a82f779 or newer
```

## 0. Prepared state (already done by Director I2, do not redo)

| Artifact | Where | Digest |
|---|---|---|
| Built candidate (marker build, native sign-in client embedded, adhoc) | `~/.mastermind/mmos_bundles/mmos-v1-integration-20261109-29a82f77-29a82f779f3d--1bba0c01/Mastermind OS.app` | `sha256:1bba0c01e9a31a1b6479ae8a1f543cb0a5622f106586a1eeffb53dc52dcc66b4` |
| Snapshot of the currently installed app (rollback anchor) | `~/.mastermind/mmos_bundles/mmos-login-repair-20261109-3652d89-3652d8907df1` | `sha256:6e00eeaaf47f40a7506c0d38b4ae327e41d4c7e8dfdcc2a389fbf0432cd57721` |
| Superseded first build (no sign-in client; kept for honesty, do NOT install) | `~/.mastermind/mmos_bundles/mmos-v1-integration-20261109-29a82f77-29a82f779f3d` | `sha256:b494b15c2078319936502466cfb0a4df9dbc9a7b920fb3cdda9ba6b3e87d6331` |

The install command refuses while the app is running (exit 4 with the human
quit step), snapshots the current bundle first (idempotent), preserves the
replaced bundle under `install-tmp-<ts>` (never deletes), and verifies the
re-observed install digest equals the source digest. Proven by tests in
`tests/test_mmos_rollback.py` (`test_install_*`, 7 tests).

## 1. HUMAN: quit the running app

Mastermind OS menu → **Quit Mastermind OS** (or Cmd-Q). The tooling never
kills or quits it. Verify from a terminal if you like:

```sh
ps ax -o pid=,comm= | grep "Mastermind OS.app" || echo "not running"
```

## 2. Install the new bundle (one command)

```sh
$R --bundle "$HOME/Applications/Mastermind OS.app" \
   install --from "$HOME/.mastermind/mmos_bundles/mmos-v1-integration-20261109-29a82f77-29a82f779f3d--1bba0c01/Mastermind OS.app" \
   --execute
```

Expected output: `installed bundle … matches source digest
sha256:1bba0c01…`, `previous bundle preserved at:
~/.mastermind/mmos_bundles/install-tmp-<ts>/Mastermind OS.app`, and the
remaining HUMAN steps. Exit 0.

Exit codes if it goes wrong: `4` the app is (or may be) running from the
current bundle — quit it and re-run; `7` executed but the re-observed digest
≠ source — previous bundle preserved at the printed path, reconcile before
retrying; `8` EFFECT_UNKNOWN — nothing more moves until reconciled by hand.

Manual fallback (only if the script is unavailable): confirm the app is
quit, `mv "$HOME/Applications/Mastermind OS.app" ~/.mastermind/mmos_bundles/manual-$(date -u +%Y%m%dT%H%M%SZ).app`,
then `ditto "$HOME/.mastermind/mmos_bundles/mmos-v1-integration-20261109-29a82f77-29a82f779f3d--1bba0c01/Mastermind OS.app" "$HOME/Applications/Mastermind OS.app"`,
then take the receipt in step 5 and require digest
`sha256:1bba0c01e9a31a1b6479ae8a1f543cb0a5622f106586a1eeffb53dc52dcc66b4`.

## 3. HUMAN: launch and take the user-path checklist (DONE_WHEN 1/3/5/6)

Launch Mastermind OS from `~/Applications` as usual. Expected honest states
at this head — **a state is a PASS only if it matches exactly; anything
shown as healthy/zero without a source is a FAIL**:

| # | Surface | Expected state at head `29a82f779` |
|---|---|---|
| a | Build details panel (bottom `Build details` disclosure) | `Source revision` = `29a82f779f3d7ad3cdfba3f07b61ef8dedad2c0d`, `Build identity` = `mmos-v1-integration-20261109-29a82f77`, `Version` 0.1.0, a `Native client` ref is present, `Transport` = `CONFIGURED / BUILT_NOT_PROVEN`. These must equal the receipt values byte-for-byte. |
| b | Sign-in (master #2344 account-only path) | The primary-account sign-in entry works: sign in, reach `signed_in`, workspace reads (Today/Fleet) become live. `#2344` ("Restore account-only sign-in and truthful Projects read states", `c4a6f298a`) is **in this build and NOT in the previously installed one** — this install is what brings it to the desktop. If the Auth0 tenant's refresh toggles are on, sign-in survives an app relaunch. An honest `Sign-in is unavailable here.` with a typed reason means the build lost its native client — FAIL, do not proceed. |
| c | Team route (DONE_WHEN 1) | Roster shows the honest **UNAVAILABLE state with a typed reason code** (`NATIVE_UNAVAILABLE` family: the Hermes gateway control socket is wedged — identify never answers; see `LANE_HERMES_DIRECTOR_B2.md` §1) — **never an empty company, never a fake roster**. The bot conversation entry shows its classified gateway state (viewer-disconnected / gateway-busy / unknown) with the reason visible. When Hermes later restarts the gateway, roster rows turn real without an app change. |
| d | Code route (DONE_WHEN 3/6) | The honest not-projected copy naming the missing source: *"This surface reads the typed T3 thread projection from MastermindMissionHost.t3ThreadProjection. That projection source is not connected on this host — no host implements it yet — so no thread state is shown or inferred."* No thread rows are invented. |
| e | Fleet & Capacity (DONE_WHEN 3) | "Original capacity receipts and run records" and "Recent Fabric runs" render as before (signed-in reads live; unknown stays unknown). The "T3 attempt fleet" block shows honestly-not-connected: *"The T3 attempt reader is not connected to this workspace."* — the desktop has no native `readT3AttemptFleet` client at this head (Director G2, SOURCE_ONLY). Invariant chips never render PROVEN without evidence. |
| f | Projects → Team delivery (DONE_WHEN 5) | The Result return section shows *"No execution return is projected yet."* — honest null, not a fabricated return, and nothing claims `accepted`. |
| g | Everywhere | No surface shows zero/healthy/green for an unknown or missing source; unknowns carry a visible reason (DONE_WHEN 6 honesty rule). |

One real user-path action is required beyond looking: e.g. open the Team
route once (its typed UNAVAILABLE reason is the live read), or complete one
sign-in round trip (b). Record which action was performed.

## 4. Post-install receipt + comparison

```sh
env -u PYTHONPATH /opt/homebrew/bin/python3.12 scripts/mmos_installed_receipt.py \
  --bundle "$HOME/Applications/Mastermind OS.app"
```

PASS: `receipt_digest` ==
`sha256:1bba0c01e9a31a1b6479ae8a1f543cb0a5622f106586a1eeffb53dc52dcc66b4`,
`source_revision.value` == `29a82f779f3d7ad3cdfba3f07b61ef8dedad2c0d` with
provenance **`embedded_marker`** (not `heuristic_scan`), `build_identity.value`
== `mmos-v1-integration-20261109-29a82f77` (also `embedded_marker`),
`codesign.signature` == `adhoc` (parity with the previous install), and
`running_app.from_this_bundle` == `true` once relaunched.

Pre-install receipt for comparison (Director I2, 2026-11-09): digest
`sha256:6e00eeaa…`, revision `3652d8907df1…` (`heuristic_scan`), identity
`mmos-login-repair-20261109-3652d89`. The delta — revision, identity,
provenance upgrade to `embedded_marker`, executable sha256 — is the install
proof.

## 5. Rollback drill (dry-run first, then real only if needed)

```sh
# Dry-run (zero changes; prints the exact steps):
$R --bundle "$HOME/Applications/Mastermind OS.app" \
   plan --to "$HOME/.mastermind/mmos_bundles/mmos-login-repair-20261109-3652d89-3652d8907df1"

# Real rollback (only after quitting the app — same HUMAN rule):
$R --bundle "$HOME/Applications/Mastermind OS.app" \
   execute --to "$HOME/.mastermind/mmos_bundles/mmos-login-repair-20261109-3652d89-3652d8907df1" \
   --execute
```

PASS: exit 0, `installed bundle … now matches archived digest
sha256:6e00eeaa…`, previous (candidate) bundle preserved under
`rollback-tmp-<ts>`. Take the receipt again (step 4 command): digest must be
`sha256:6e00eeaa…`. Relaunch and confirm the Build details panel shows
`3652d890…` / `mmos-login-repair-20261109-3652d89`.

## 6. What to paste to GitHub issue #983

Post as **text** (fenced block), one post per install/rollback event:

1. The full post-install receipt JSON (step 4) — bundle path, digest,
   provenance, running state.
2. The checklist verdicts (step 3, a–g) with the one real user-path action
   performed and by whom.
3. If the rollback drill ran: the post-rollback receipt JSON and the
   preserved-bundle paths.

The receipts contain no secrets (no keychain material, no tokens). Do not
attach plists beyond the four identity keys the script emits.

## 7. Standing constraints (unchanged)

The tooling never kills/quits/launches the app; quitting is always the human
step. Never delete the archive or `install-tmp-`/`rollback-tmp-` directories.
`--execute` is the only mutating flag; every command without it is a dry-run.
Unknown is unknown — report typed reasons verbatim, never paraphrase them
into health.
