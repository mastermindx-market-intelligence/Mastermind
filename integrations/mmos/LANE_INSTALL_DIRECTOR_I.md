# Lane: installed-version receipts + rollback — Director I ledger

Branch `t3/installed-receipts-rollback` (worktree
`~/.t3/worktrees/Mastermind/t3-7bcbbc38`), base `7bbac9278` off
`t3/t3-hermes-restart-recovery`, program pin
`~/.hermes/profiles/engineering/mmos/T3_HANDOFF_V2.md` DONE_WHEN row 7
("installed-version receipts + rollback"; §0 "a green PR is not the goal",
§7 hard constraints). No push, no PR, no edits outside this lane's files.
Companion procedure doc: `integrations/mmos/INSTALL_RECEIPTS_AND_ROLLBACK.md`.

## Deliverables

| File | What |
|---|---|
| `scripts/mmos_installed_receipt.py` | READ-ONLY observer; emits `mastermind.installed_receipt/v1` (bundle path, Info.plist identity keys, executable sha256/size/mtime, embedded revision+identity with honest provenance, codesign display, running-process match, observed_at/host, content `receipt_digest`). Exit 0 with honest unknowns; exit 2 malformed args only. |
| `scripts/mmos_rollback.py` | `snapshot` (idempotent by receipt digest, atomic tmp-then-rename, same-name/different-bytes disambiguation) / `plan` (exact steps, zero changes) / `execute` (dry-run default; mutations only with `--execute`; refuses while the app is or may be running from the current bundle — prints the human quit step, never kills; previous bundle always preserved under `rollback-tmp-<ts>`; archive digest-verified pre-move; `--to` containment enforced). |
| `tests/mmos_fake_bundle.py` | Hermetic fake `.app` builder (XML/binary plist; fake Mach-O-ish executable carrying marker and/or the real Readiness rodata blob incl. the three real-world decoy hashes). |
| `tests/test_mmos_installed_receipt.py` | 16 tests. |
| `tests/test_mmos_rollback.py` | 11 tests (incl. tree-hash zero-change assertions on dry-runs/refusals). |
| `integrations/mmos/INSTALL_RECEIPTS_AND_ROLLBACK.md` | Procedure: identity model (CI env from `mastermind-os.yml` + local build command), receipt taking, what counts as installed consumer proof, #983 evidence (text only, this lane posts nothing), rollback walkthrough + exit codes, and the verbatim src-tauri marker patch proposal. |
| This ledger | Evidence classification + handoffs. |

Reuse-first: the repo grep (`installed_receipt|install receipt|rollback|Mastermind OS.app|tauri build|MM_BUILD_IDENTITY`, py/md/sh/rs/ts, node_modules excluded) found no existing OS-app install/receipt/rollback machinery — only research-doc narrative and the unrelated headless-control installer ceremony. `integrations/session_bridge/installed*.py` confirmed to be Executive CeoIngress session transport, unrelated (not reused). Existing reused facts: `build.rs` identity law (charset/length/40-hex), CI env values, the `readiness` command + Build details UI panel (`App.tsx:2600`, `App.tsx:6147-6159`).

## Exact commands + counts

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest \
  tests/test_mmos_installed_receipt.py tests/test_mmos_rollback.py
→ 27 passed in 4.10s   (16 receipt + 11 rollback)

env -u PYTHONPATH /opt/homebrew/bin/python3.12 scripts/mmos_installed_receipt.py \
  --bundle "$HOME/Applications/Mastermind OS.app"            # live, read-only
env -u PYTHONPATH /opt/homebrew/bin/python3.12 scripts/mmos_installed_receipt.py \
  --bundle "$HOME/Applications/Mastermind OS.app.bak-mmos-office-connection-06ef56a3"

git apply --check <marker patch extracted from the md>       # PATCH_APPLIES_CLEAN
CLI smoke on temp dirs: snapshot rc=0, plan rc=0, execute-without-flag rc=3
(with the real app running), traversal --to rc=6, missing bundle rc=1.
```

## What is installed right now (m2studio, OBSERVED_LIVE 2026-11-09 ~09:44 UTC)

The mission brief said `/Applications`; the app is actually installed under
`~/Applications` (both paths stat-checked; `/Applications` has no Mastermind
OS). Someone previously performed one ad-hoc backup-based rollback (the
`.bak-mmos-office-connection-06ef56a3` bundle); this lane studied it
read-only and did not modify either bundle.

**Current install** (`~/Applications/Mastermind OS.app`, running, PID 73195):

```json
{
  "schema": "mastermind.installed_receipt/v1",
  "bundle_path": "/Users/chriswong/Applications/Mastermind OS.app",
  "bundle_exists": true,
  "info_plist": {
    "CFBundleIdentifier": "com.mastermind.os",
    "CFBundleShortVersionString": "0.1.0",
    "CFBundleVersion": "0.1.0",
    "CFBundleExecutable": "mastermind-os"
  },
  "executable": {
    "path": "/Users/chriswong/Applications/Mastermind OS.app/Contents/MacOS/mastermind-os",
    "sha256": "12f669e167ae339f20c2e32dc63627d0fcb1633947905c58ed96af8cb350b726",
    "size_bytes": 18788176,
    "mtime": "2026-11-09T09:03:23.670304+00:00"
  },
  "source_revision": {"value": "3652d8907df1738de551dd3032b42aa2a2acb482", "provenance": "heuristic_scan"},
  "build_identity": {
    "value": "mmos-persistent-login-20261109-3652d89",
    "provenance": "heuristic_scan",
    "detail": "heuristic scan trimmed adjacent rodata literal 'native' from the raw identity capture"
  },
  "codesign": {"status": "signed", "identifier": "mastermind_os-2a3078611ef731a5", "team_identifier": null, "signature": "adhoc"},
  "running_app": {"from_this_bundle": true, "pids": [73195], "detail": "ps comm matches this bundle's executable path"},
  "observed_at": "2026-11-09T09:44:14.742+00:00",
  "host": "m2studio",
  "receipt_digest": "sha256:1272d17417d11ee69e5a387168f9aa7aa8fd3f027211d822200201e0e46f6d90"
}
```

**Prior backup** (`~/Applications/Mastermind OS.app.bak-mmos-office-connection-06ef56a3`, not running):

```json
{
  "schema": "mastermind.installed_receipt/v1",
  "bundle_path": "/Users/chriswong/Applications/Mastermind OS.app.bak-mmos-office-connection-06ef56a3",
  "bundle_exists": true,
  "info_plist": {
    "CFBundleIdentifier": "com.mastermind.os",
    "CFBundleShortVersionString": "0.1.0",
    "CFBundleVersion": "0.1.0",
    "CFBundleExecutable": "mastermind-os"
  },
  "executable": {
    "path": "/Users/chriswong/Applications/Mastermind OS.app.bak-mmos-office-connection-06ef56a3/Contents/MacOS/mastermind-os",
    "sha256": "9a1f80af2535d04da43a551fe6b4ed036014061b30210d94ccc78b815d67ef6d",
    "size_bytes": 18654880,
    "mtime": "2026-11-09T01:49:49.842901+00:00"
  },
  "source_revision": {"value": "06ef56a39c085af72bcbf0866db8e43f99cd6034", "provenance": "heuristic_scan"},
  "build_identity": {
    "value": "mmos-office-connection-06ef56a3-20261109-01a1a4bf",
    "provenance": "heuristic_scan",
    "detail": "heuristic scan trimmed adjacent rodata literal 'native' from the raw identity capture"
  },
  "codesign": {"status": "signed", "identifier": "com.mastermind.os", "team_identifier": null, "signature": "adhoc"},
  "running_app": {"from_this_bundle": null, "pids": [73195], "detail": "process(es) share only the executable name; path unknown"},
  "observed_at": "2026-11-09T09:44:20.256+00:00",
  "host": "m2studio",
  "receipt_digest": "sha256:ae88a0b61c5bcc525cc3347ad6eb3381bb694c38c9624e49084527d1817ce7bf"
}
```

No secrets appear in either receipt (no keychain/auth material read). Note
neither install carries the release-candidate stack heads from HANDOFF §1
(`bd91db1e` master / `2f3deba2` PR #2338): the installed revision
`3652d890` is its own generation, identity-tagged `mmos-persistent-login…`
— i.e. the installed app is a local lane build, and installed-consumer-proof
for the accepted generation remains open (see SOURCE_ONLY).

## Evidence classification

| Claim | Class |
|---|---|
| Receipt schema/determinism (digest stable across observers/plist encodings; excluded volatile fields) | PROVEN_BY_TEST |
| `embedded_marker` extraction (proposed `MM_RECEIPT:{json}`) incl. marker-beats-blob precedence | PROVEN_BY_TEST |
| `heuristic_scan` extraction: version-anchored, decoy-resistant, seam-trimmed, honest `unknown` on absence/ambiguity/empty-identity | PROVEN_BY_TEST (and regression-locked to the two real blobs) |
| codesign parse (signed/unsigned/unavailable) and running-app exact/ambiguous/absent/ps-failure states | PROVEN_BY_TEST |
| Missing bundle → honest unknown receipt, exit 0; malformed args exit 2 | PROVEN_BY_TEST |
| Snapshot: archive layout, idempotency (no second copy, mtimes untouched), same-name disambiguation, missing-bundle error | PROVEN_BY_TEST |
| Dry-run purity: `plan` and flagless `execute` leave both trees bit-identical (tree hash) — incl. while an app is "running" | PROVEN_BY_TEST |
| Refusals: no `--execute` (rc 3), app-from-current-bundle or ambiguous (rc 4, human step printed, never kills), archive digest mismatch (rc 5), `--to` traversal/escape incl. absolute paths (rc 6) | PROVEN_BY_TEST |
| Real execute happy path: install from archive, digest match, previous bundle preserved, archive intact | PROVEN_BY_TEST (fake bundles; real-/Applications execute intentionally NOT run) |
| Both live receipts above (values, digests, adhoc signatures, PID 73195) | OBSERVED_LIVE |
| `~/Applications` (not `/Applications`) install location; prior ad-hoc `.bak` rollback | OBSERVED_LIVE |
| `git apply --check` PASS for the marker patch at base `7bbac9278` | OBSERVED_LIVE (procedure artifacts below) |
| Marker patch in installed binaries (`embedded_marker` provenance on a real build) | SOURCE_ONLY — awaits integrator |
| Rollback of the REAL installed app; #983 receipt posting; installed-consumer-proof for the accepted generation | SOURCE_ONLY — owner actions (see handoffs) |

## Integrator handoffs

1. **src-tauri marker patch** (verbatim unified diff in
   `INSTALL_RECEIPTS_AND_ROLLBACK.md` §6; `git apply --check` PASS at base
   `7bbac9278`): adds `install_marker: MM_RECEIPT_MARKER` to `Readiness` in
   `main.rs`. No `build.rs` change needed (rustc-env + charset assertions
   already guarantee a well-formed marker). Additive to the frontend contract;
   optionally surface it in the Build details panel. Once shipped, receipts
   upgrade from `heuristic_scan` to `embedded_marker` with zero tool changes.
2. **CI**: `mastermind-os.yml` `native-macos` already sets
   `MM_SOURCE_REVISION=${{ github.sha }}`,
   `MM_BUILD_IDENTITY=ci-native-<run_id>-<run_attempt>` — no workflow change
   required for receipts. If a CI build is ever installed, take its receipt
   with `--bundle` and attach to #983 per the procedure doc.
3. **Owner rollback runbook**: before replacing any installed build,
   `snapshot` it; after install, receipt + Build-details panel + one real
   user-path action (procedure doc §3/§5). The lane deliberately did not
   execute a real rollback (app currently running; lane constraint).

## Not done, and why

- No push / PR / #983 post: lane instruction (commit-only) and no GitHub
  posting authority here.
- No `execute` against the real `~/Applications`: forbidden in this lane;
  additionally the app is live from that exact bundle (receipt proves it), so
  the tool itself would print the human quit step and refuse.
- Marker patch not applied: `src-tauri/**` is integrator-owned; proposal
  delivered verified-verbatim only.
- No fabric/flash leaf dispatched: bounded single-context lane; the fixture
  builder and plist tests were cheaper inline than a dispatch round-trip
  (smallest sufficient tool envelope; this session is already a delegated
  child).
- Found-and-fixed during lane (recorded for honesty): live CLI smoke exposed
  dry-run-before-running-check ordering (rc 4 instead of 3 while an app
  merely shares the executable basename); fixed with a regression test
  (`test_dry_run_allowed_even_while_app_running`).
