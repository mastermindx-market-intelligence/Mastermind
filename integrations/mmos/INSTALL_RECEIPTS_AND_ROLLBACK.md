# Mastermind OS — installed-version receipts + rollback (DONE_WHEN row 7)

Owner: Director I lane (`t3/installed-receipts-rollback`), Fable COO program
(T3_HANDOFF_V2 §0 row 7). Program law: a green PR/CI run is not the goal;
DONE requires **installed consumer proof** — "screenshots don't count".

Tooling (this lane, hermetically tested):

* `scripts/mmos_installed_receipt.py` — READ-ONLY observer of an installed bundle.
* `scripts/mmos_rollback.py` — archive snapshot + dry-run-default rollback
  plan/executor (never kills/quits/launches the app; preserves the previous
  bundle; refuses `--execute` while the app may be running from the current
  bundle).

Nothing here grants CI, release, account or host-mutation authority beyond
reading installed bundles and the operator's explicit `--execute`.

## 1. How a build gets its identity

`app/mastermind_os/src-tauri/build.rs` requires at build time:

| Env var | Constraint (enforced by build.rs) | Meaning |
|---|---|---|
| `MM_SOURCE_REVISION` | exactly 40 hex chars | full Git object id of the built source |
| `MM_BUILD_IDENTITY` | 1..160 chars of `[A-Za-z0-9._:-]` | who/what produced this binary |

CI (`.github/workflows/mastermind-os.yml`, job `native-macos`) sets:

```yaml
MM_SOURCE_REVISION: ${{ github.sha }}
MM_BUILD_IDENTITY: ci-native-${{ github.run_id }}-${{ github.run_attempt }}
```

CI builds are unsigned (`tauri build --ci --no-sign`) and are **not** release
or installation acceptance — the workflow says so itself.

A local/installed build must repeat the same discipline, e.g.:

```sh
MM_SOURCE_REVISION="$(git rev-parse HEAD)" \
MM_BUILD_IDENTITY="mmos-<lane-name>-$(date -u +%Y%m%d)-$(git rev-parse --short=8 HEAD)" \
  npm run tauri build   # from app/mastermind_os, with the pinned toolchain
```

The two builds installed on m2studio before the L3 install followed exactly this
shape (`mmos-persistent-login-20261109-3652d89`,
`mmos-office-connection-06ef56a3-20261109-01a1a4bf`). The current install is
recorded in §1.1.

### 1.1 Installed receipts ledger (m2studio)

Read-only observation, 2026-11-10 (host `m2studio`). Each fact cites the
command that produced it.

| # | `build_identity` | `source_revision` | Origin branch | `receipt_digest` | State |
|---|---|---|---|---|---|
| 1 | `mmos-l3-install-20261110-5420bb17` | `5420bb1714cb99ef3e7fcaec766f3bd86af1b2de` | `t3/mmos-v2-l3` | `sha256:54c775aedf384b709604734a3d9dc1091495d01ebcc70f78570cbfa85d925671` | superseded by #2; kept as the rollback anchor |
| 2 | `mmos-l3-install2-20261110-5420bb17` | `5420bb1714cb99ef3e7fcaec766f3bd86af1b2de` | `t3/mmos-v2-l3` | `sha256:d59b57eda2a87f059d32a6f9f9a8b68495931d10c4ff25e7e1fbcea59ce0515d` | **currently installed** at `~/Applications/Mastermind OS.app` |

Install #2 facts (provenance `embedded_marker` for both identity fields):

```sh
env -u PYTHONPATH /opt/homebrew/bin/python3.12 scripts/mmos_installed_receipt.py \
  --bundle "$HOME/Applications/Mastermind OS.app"
```

* `source_revision` = `5420bb1714cb99ef3e7fcaec766f3bd86af1b2de`,
  `build_identity` = `mmos-l3-install2-20261110-5420bb17`,
  executable sha256 `302bbf36ae55…`, digest
  `sha256:d59b57edad…ce0515d`; app running from this exact bundle
  (`from_this_bundle: true`) at observation.
* Source commit is real and contained: `git cat-file -t 5420bb1714cb99ef…`
  → `commit`; `git merge-base --is-ancestor 5420bb1714cb99ef… origin/t3/mmos-v2-l3`
  → true (and it is the branch head: `git rev-parse origin/t3/mmos-v2-l3` →
  `5420bb1714cb99ef3e7fcaec766f3bd86af1b2de`, a merge of `origin/master` into
  `t3/mmos-l3-release-install`). It is also already on trunk
  (`origin/feat/mmos-v1-integration-t3`); `origin/feat/mmos-v1-integration-t3..origin/t3/mmos-v2-l3`
  is empty.

**Rollback entry for install #2.** The replaced bundle (install #1) was
preserved by the installer at
`~/.mastermind/mmos_bundles/install-tmp-20261110T015848Z/Mastermind OS.app`,
bytes-equal to the archived install #1 (same digest
`sha256:54c775aedf384b709604734a3d9dc1091495d01ebcc70f78570cbfa85d925671`
from `scripts/mmos_installed_receipt.py` on both). The deterministic rollback
target is the install #1 archive; dry-run plan returns rc 0 with the archive
digest check `PASS` and changes nothing:

```sh
env -u PYTHONPATH /opt/homebrew/bin/python3.12 scripts/mmos_rollback.py \
  --bundle "$HOME/Applications/Mastermind OS.app" \
  plan --to "$HOME/.mastermind/mmos_bundles/mmos-l3-install-20261110-5420bb17-5420bb1714cb"
```

`--execute` remains the §5 procedure with its HUMAN quit step (rc 4 while the
app runs) and re-observation of digest
`sha256:54c775aed…d925671`. Rolling further back to
`mmos-login-repair-20261109-3652d89` (revision
`3652d8907df1738de551dd3032b42aa2a2acb482`, digest
`sha256:6e00eeaaf47f40a7506c0d38b4ae327e41d4c7e8dfdcc2a389fbf0432cd57721`) is
the archive directory
`~/.mastermind/mmos_bundles/mmos-login-repair-20261109-3652d89-3652d8907df1`;
that bundle is also preserved at `install-tmp-20261110T015231Z` (replaced by
install #1).

No receipt row here proves a *user-path* action; §3 item 3 is still owed by the
owning lane, and a receipt is not acceptance.

## 2. Taking an installed receipt

```sh
env -u PYTHONPATH /opt/homebrew/bin/python3.12 scripts/mmos_installed_receipt.py \
  --bundle "$HOME/Applications/Mastermind OS.app" > receipt.json
```

(The lane brief names `/Applications/Mastermind OS.app`; on this Mac the app
is actually installed under `~/Applications` — pass `--bundle` explicitly.
The script default remains `/Applications/Mastermind OS.app`.)

Emits `mastermind.installed_receipt/v1`: bundle path/existence, Info.plist
identity keys, main executable path+sha256+size+mtime, embedded
source revision and build identity, codesign display status, whether a live
process runs from this exact bundle, observed_at, host, and a
`receipt_digest`.

**Provenance labels are honest, never fabricated:**

* `embedded_marker` — the binary contains `MM_RECEIPT:{"source_revision":…,
  "build_identity":…}` (see §6; requires the integrator to land the marker
  patch). Deterministic, authoritative.
* `heuristic_scan` — no marker; the revision was found by anchoring on the
  bundle's own `CFBundleShortVersionString` immediately preceding a 40-hex
  token (the real Readiness rodata layout `<version><rev><identity>`; a bare
  40-hex scan cannot even see it — the preceding `0` of `0.1.0` is itself a
  hex digit — and would collide with std-backtrace build ids). Calibrated
  against both real installed builds on 2026-11-09; ambiguous layouts are
  rejected. Identity extraction trims the documented adjacent rodata literal
  (`native`); the receipt carries a `detail` note when it did.
* `unknown` — no honest extraction was possible. **Unknown is unknown.**

**Digest semantics:** `receipt_digest` covers schema, Info.plist identity
values, executable sha256+size, and the revision/identity
value+provenance — deliberately *excluding* paths, mtimes, codesign text,
running-process state, observed_at and host, so the same bytes hash equally
in `/Applications`, `~/Applications` and the rollback archive. Cross-check a
heuristic receipt against the app's own report before trusting it (§3).

## 3. What counts as "installed consumer proof"

All three, for one build:

1. **Bundle receipt** from the installed location (§2) whose
   `source_revision` equals the commit accepted for release and whose
   `build_identity` names the producing build (CI run or local lane tag).
2. **The running app reports the same values.** The app's Build details panel
   (`<details className="build-details">`, `app/mastermind_os/src/App.tsx`,
   fed by the `readiness` Tauri command → `source_revision` /
   `build_identity`) must show exactly the receipt's values. Until the marker
   patch lands, heuristic receipts must be reconciled against this panel.
3. **One real user-path action** through the installed app (e.g. one roster
   read / one conversation open / one T3 deep-link), observed by a human or
   the owning lane's real-path check — not a screenshot.

A green CI build, an unsigned CI package, or an app that merely launches
satisfies none of these.

## 4. Attaching evidence to issue #983

Post the receipt JSON as text (fenced block) to GitHub issue #983 with:
bundle path, digest, provenance, whether the app was running, and the
user-path action performed. This lane's scripts never post anywhere; posting
is the operator's text action. Receipts contain no secrets (no keychain
material, no tokens) — do not attach plists beyond the four identity keys the
script emits.

## 5. Rollback procedure

Archive root default `~/.mastermind/mmos_bundles/` (`--archive-root` to
override; used for all tests with temp dirs).

```sh
R="env -u PYTHONPATH /opt/homebrew/bin/python3.12 scripts/mmos_rollback.py"

# 0. Archive EVERY build before replacing it (idempotent by receipt digest):
$R --bundle "$HOME/Applications/Mastermind OS.app" snapshot

# 1. Inspect the exact steps (zero filesystem changes):
$R --bundle "$HOME/Applications/Mastermind OS.app" plan --to <archive-dir-or-receipt.json>

# 2. HUMAN: quit Mastermind OS (Cmd-Q). The tool never kills/quits it, and
#    refuses --execute while a process may be running from the current bundle.

# 3. Apply (only with the explicit flag):
$R --bundle "$HOME/Applications/Mastermind OS.app" execute --to <archive-dir> --execute

# 4. Verify: the script re-observes and compares digests itself; then do §3
#    (relaunch is a human step; confirm the Build details panel + one action).
```

Exit codes: `0` ok / already archived / plan; `1` operational error;
`2` malformed args; `3` execute refused — no `--execute` (dry-run);
`4` refused — app running/ambiguous from current bundle (human quit step);
`5` refused — archive digest verification failed (tampered/corrupt);
`6` refused — `--to` resolves outside `--archive-root` (traversal);
`7` executed but re-observed install ≠ archive (previous bundle preserved);
`8` EFFECT_UNKNOWN — mid-rollback failure, previous bundle preserved at the
printed path.

Safety properties (proven by tests, not promises): dry-run makes zero
filesystem changes; the current bundle is always *moved* to
`rollback-tmp-<ts>` (never deleted); the archived bundle is digest-verified
against its stored receipt before anything moves.

### 5.1 Installing a fresh build (Director I2)

The mirror of rollback for placing a newly built `.app` at the install
location — one command, same safety model (dry-run default, rc 3; refuses
while the app is/may be running, rc 4; never kills/quits/launches):

```sh
$R --bundle "$HOME/Applications/Mastermind OS.app" \
   install --from <built-or-archived "Mastermind OS.app"> --execute
```

It requires the source to be an existing `.app` that is neither the install
target nor nested with it (rc 2 otherwise), snapshots the current bundle
first (idempotent §5 step 0), preserves the replaced bundle under
`install-tmp-<ts>`, and requires the re-observed install digest to equal the
source bundle's receipt digest (rc 7 mismatch / rc 8 EFFECT_UNKNOWN with the
previous bundle preserved). A dry-run prints the INSTALL PLAN and changes
nothing — not even the snapshot. The full human runbook (launch, honest
user-path checklist, rollback drill, #983 evidence) is
`integrations/mmos/INSTALLED_ACCEPTANCE_SCRIPT.md`.

## 6. src-tauri `MM_RECEIPT` marker — LANDED at `6d5b2f737`

**Status correction (2026-11-10):** this patch is not merely proposed — it
landed in `app/mastermind_os/src-tauri/src/main.rs` at commit `6d5b2f737`
(`grep -n MM_RECEIPT_MARKER app/mastermind_os/src-tauri/src/main.rs` →
`install_marker` field, `MM_RECEIPT_MARKER` const), and the installed build
`mmos-l3-install2-20261110-5420bb17` reports
`provenance: embedded_marker` for both identity fields (§1.1). The original
proposal text is kept below as the authoring record.

At authoring time src-tauri was integrator-owned and this lane did **not** edit it. The patch below
makes receipts deterministic (`embedded_marker`) and simultaneously exposes
the marker through the running app's `readiness` payload (referencing the
constant in `Readiness` guarantees the linker keeps the bytes in the
executable). `build.rs` needs **no change**: it already emits
`cargo:rustc-env` for both vars, and its charset assertion
(`[A-Za-z0-9._:-]`) already guarantees the embedded JSON stays well-formed.
`scripts/mmos_installed_receipt.py` already parses this marker today.

```diff
diff --git a/app/mastermind_os/src-tauri/src/main.rs b/app/mastermind_os/src-tauri/src/main.rs
index 5aa9e4e4d..8a16a6b57 100644
--- a/app/mastermind_os/src-tauri/src/main.rs
+++ b/app/mastermind_os/src-tauri/src/main.rs
@@ -20,11 +20,25 @@ struct Readiness {
     version: &'static str,
     source_revision: &'static str,
     build_identity: &'static str,
+    install_marker: &'static str,
     transport: &'static str,
     state: &'static str,
     native_client_ref: Option<String>,
 }
 
+/// One greppable line embedded in the executable so installed-bundle receipts
+/// (scripts/mmos_installed_receipt.py) can extract the build identity with
+/// provenance `embedded_marker` instead of a heuristic rodata scan. Referenced
+/// by `Readiness` so the linker always keeps the bytes in the binary; the
+/// build.rs charset assertion keeps the embedded JSON well-formed.
+const MM_RECEIPT_MARKER: &str = concat!(
+    "MM_RECEIPT:{\"source_revision\":\"",
+    env!("MM_SOURCE_REVISION"),
+    "\",\"build_identity\":\"",
+    env!("MM_BUILD_IDENTITY"),
+    "\"}"
+);
+
 fn readiness_from_client_id(client_id: Option<&str>) -> Result<Readiness, &'static str> {
     let native_client_ref = match client_id {
         None => None,
@@ -40,6 +54,7 @@ fn readiness_from_client_id(client_id: Option<&str>) -> Result<Readiness, &'stat
         version: env!("CARGO_PKG_VERSION"),
         source_revision: env!("MM_SOURCE_REVISION"),
         build_identity: env!("MM_BUILD_IDENTITY"),
+        install_marker: MM_RECEIPT_MARKER,
         transport: if native_client_ref.is_some() {
             "CONFIGURED"
         } else {
```

Notes for the integrator: additive field (frontend `BuildReceipt` typing is
structural; existing tests unaffected — optionally surface `install_marker`
in the Build details panel); no behavior, auth, transport or release change.

## 7. Constraints honored

Read-only against installed bundles (`ls`, `open(rb)`, `codesign -dv`, `ps`);
never modified/moved/launched/killed anything under `/Applications` or
`~/Applications`; no edits to `src-tauri/**`, `executive_runtime.py`,
`worker_adapter.py`, routes JSON, `~/.hermes/**`, or secrets; no new daemon,
listener or registry; unknown observations are emitted as `unknown`.
