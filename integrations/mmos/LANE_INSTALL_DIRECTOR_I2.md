# Lane ledger — Director I2: installed acceptance PREPARATION (DONE_WHEN 6/7)

Owner: Director I2 (GLM-5.3 sub-orchestrator, successor of Director I on
this seam), Fable COO program. Branch `t3/installed-acceptance-prep` at head
`29a82f779f3d7ad3cdfba3f07b61ef8dedad2c0d` (= merged head of
`t3/t3-hermes-restart-recovery` = origin `feat/mmos-v1-integration-t3`
bytes). No push, no PR, no other worktree touched, nothing under
`~/.hermes`, `/Applications` or `~/Applications` modified, moved, killed or
launched (snapshot COPIES only, into `~/.mastermind/mmos_bundles/`).
`--execute` was never passed against any real bundle.

Mission: the gap audit ("no DONE_WHEN row is PROVEN_INSTALLED; the installed
app is master build 3652d89"). This lane produced everything up to, but NOT
including, replacing the running app: a real native build of this head with
its receipt, the snapshot + rollback plan for the current install, the
`install` subcommand + tests, and the user-path acceptance script
(`INSTALLED_ACCEPTANCE_SCRIPT.md`). The install itself requires the human to
quit the running app — handed to the principal, not executed here.

## 1. Build (real, from this worktree)

Command shape: the mission's `npm run tauri build` does not exist in
`app/mastermind_os/package.json` (scripts: dev/build/typecheck/test only);
the repo-documented shape is the CI workflow's direct binary call
(`.github/workflows/mastermind-os.yml`, job `native-macos`). Used:

```sh
cd app/mastermind_os && npm ci --no-audit --no-fund
MM_SOURCE_REVISION=29a82f779f3d7ad3cdfba3f07b61ef8dedad2c0d \
MM_BUILD_IDENTITY=mmos-v1-integration-20261109-29a82f77 \
MM_NATIVE_REFRESH_ENABLED=1 MM_NATIVE_CLIENT_ID=<public client id> \
./node_modules/.bin/tauri build --ci --bundles app -- --locked
```

- Toolchain: node v26.5.0 (CI pins 22.23.3; `package.json` pins no engines,
  build green), tauri-cli 2.11.5, rustc/cargo 1.99.0 (Homebrew; equals the
  CI `RUSTUP_TOOLCHAIN` version line). `--no-sign` was NOT used: no signing
  identity is configured in `tauri.conf.json`, so the bundler applies its
  default **adhoc** signature — parity with the installed bundle's
  `Signature=adhoc` (both `Identifier=mastermind_os-2a3078611ef731a5`,
  `CodeDirectory flags=0x20002(adhoc,linker-signed)`), unlike CI's
  deliberately unsigned package.
- **Deviation from the mission's literal command, and why:** the first build
  followed the mission env exactly (no `MM_NATIVE_CLIENT_ID`) and produced a
  receipt-perfect bundle (`embedded_marker`, digest
  `sha256:b494b15c2078319936502466cfb0a4df9dbc9a7b920fb3cdda9ba6b3e87d6331`,
  archived) — but `auth.rs` keeps native sign-in honestly `unconfigured`
  without the client id (`Inner::new(option_env!("MM_NATIVE_CLIENT_ID"))`;
  the app boots, the entry would read "Sign-in is unavailable here."),
  failing the mission's own acceptance item (d) "sign-in path per master
  #2344 works". Rebuilt with the public Auth0 client id embedded — the same
  convention as the two prior lane installs (strings-verified in the
  installed binary; the id is deliberately not stored in the repo and is not
  written into any committed file). The client-id build is THE candidate.
- Build log: `Finished release profile in 1m34s` (first build; rebuild
  incremental), exit 0, warnings only. Bundle:
  `app/mastermind_os/src-tauri/target/release/bundle/macos/Mastermind OS.app`
  (worktree path; 19M, executable 18,892,384 bytes).

### Candidate receipt (the build to install) — OBSERVED_LIVE 2026-11-09

```json
{
  "source_revision": {"value": "29a82f779f3d7ad3cdfba3f07b61ef8dedad2c0d", "provenance": "embedded_marker"},
  "build_identity": {"value": "mmos-v1-integration-20261109-29a82f77", "provenance": "embedded_marker"},
  "executable": {"sha256": "c26fec2486dd11a604956024d7636e438e99b1148fee3c2f8ebbf10dd0d9ea5d", "size_bytes": 18892384},
  "codesign": {"status": "signed", "identifier": "mastermind_os-2a3078611ef731a5", "signature": "adhoc"},
  "receipt_digest": "sha256:1bba0c01e9a31a1b6479ae8a1f543cb0a5622f106586a1eeffb53dc52dcc66b4"
}
```

**Marker verdict: PROVEN_IN_REAL_BUILD.** The receipt shows provenance
`embedded_marker` (Director I's SOURCE_ONLY item closed); `strings` finds
exactly one `MM_RECEIPT:{"source_revision":"29a82f77…","build_identity":
"mmos-v1-integration-20261109-29a82f77"}` line in the binary, with the
legacy `<version><rev><identity>` rodata blob still adjacent — the marker
wins per the receipt parser's precedence. Marker first proven by the
mission's exact command (first build), then reproduced on the candidate.

## 2. Snapshot + plan of the CURRENT install — OBSERVED_LIVE

`snapshot` of `~/Applications/Mastermind OS.app` (copy into
`~/.mastermind/mmos_bundles/` only):

- Archive dir: `mmos-login-repair-20261109-3652d89-3652d8907df1`
- Stored digest `sha256:6e00eeaaf47f40a7506c0d38b4ae327e41d4c7e8dfdcc2a389fbf0432cd57721`;
  re-observing the archived copy returns the same digest (bytes confirmed).
- Snapshot receipt highlights: revision `3652d8907df1738de551dd3032b42aa2a2acb482`
  (`heuristic_scan` — no marker in that generation), identity
  `mmos-login-repair-20261109-3652d89` (`heuristic_scan`), exec sha256
  `f10f2ab3…`, adhoc, running-from-this-bundle `true` (pid 26675).

`plan --to <snapshot dir>`: rc 0, prints the 6-step plan with the HUMAN quit
step, archive digest check PASS, reversible move to
`rollback-tmp-<ts>`, copy-back, re-receipt requirement, relaunch
confirmation. Full output in the acceptance script §5; zero changes made
(dry-run).

`execute` WITHOUT `--execute` against the real install: **rc 3**,
"EXECUTE REFUSED: --execute was not provided; this was a dry-run." — while
the app runs, the plan text itself names the human quit step. The rc-4
running refusal (which requires `--execute`, never passed here against the
real bundle) is PROVEN_BY_TEST (`test_execute_refused_when_app_runs_from_current_bundle`
and the new `test_install_refused_when_app_runs_from_current_bundle`).

Drift vs Director I's ledger (both OBSERVED_LIVE): the install was replaced
again after Director I's observation — identity is now
`mmos-login-repair-20261109-3652d89` (was `mmos-persistent-login…`), exec
sha256 `f10f2ab3…` (was `12f669e1…`), pid 26675 (was 73195); revision
unchanged `3652d890` (= master, #2297 "installable host-bound GitHub App
native plugin"; NOT #2344 — `c4a6f298a` "Restore account-only sign-in…"
landed on master AFTER it and is in this candidate but not in the installed
app). A second backup `~/Applications/Mastermind OS.app.bak-persistent-login-3652d89`
now exists beside Director I's `.bak-mmos-office-connection…` (both
re-observed read-only; digests match Director I's recorded receipts).

## 3. `install` subcommand (script change) + tests

`scripts/mmos_rollback.py` gained `install --from <built .app> [--execute]`:
observes the source bundle (must be an existing `.app`, not the install
target nor nested with it → rc 2), prints a dry-run INSTALL PLAN by default
(rc 3, zero filesystem changes — not even a snapshot), and under
`--execute` refuses while the app is (or may be) running from the current
bundle (rc 4, human quit step), snapshots the current bundle first
(idempotent by digest), moves it aside under `install-tmp-<ts>` (never
deletes), copies the source in, and requires the re-observed install digest
to equal the source digest (rc 7 mismatch, rc 8 EFFECT_UNKNOWN, previous
bundle preserved). Exit-code table and safety properties unchanged; fresh
install (no current bundle) supported without tmp/snapshot side effects
(caught by test, fixed).

7 new tests in `tests/test_mmos_rollback.py` (dry-run purity via tree
hashes on both trees, running refusal, self-install guard, bad-source args
error, full execute with snapshot+preserve+digest verification, fresh
install).

## 4. Exact commands + counts

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest \
  tests/test_mmos_installed_receipt.py tests/test_mmos_rollback.py
→ 34 passed in 8.00s   (16 receipt + 11 rollback + 7 install)

Live, read-only: receipts of the installed app, both .bak bundles, the
archived snapshot copy, and both builds (all recorded above/below).
Mutations performed: snapshot ×3 into ~/.mastermind/mmos_bundles/ (two
builds + the current install) — nothing else; no --execute anywhere.
```

## 5. Evidence classification

| Claim | Class |
|---|---|
| Real build at head `29a82f779` with `embedded_marker` provenance (marker patch works in a real tauri build; `env!`/`concat!` bytes present, strings-verified once, receipt-verified twice) | OBSERVED_LIVE (upgrade of Director I's SOURCE_ONLY) |
| Candidate receipt values (revision/identity/digest/adhoc parity) | OBSERVED_LIVE |
| Current install snapshot + digest-stable archived copy; plan rc 0; flagless execute rc 3 | OBSERVED_LIVE |
| Install state drift (login-repair build, pid 26675, second .bak, #2344 not in installed rev) | OBSERVED_LIVE |
| `install` subcommand safety properties (dry-run purity, running refusal, self-install guard, snapshot-first, preserve, digest verify, fresh install) | PROVEN_BY_TEST (7 tests; real install deliberately NOT run) |
| rc-4 refusal while the real app runs | PROVEN_BY_TEST (real-bundle `--execute` forbidden in this lane) |
| Installed acceptance itself (install + launch + checklist a–g + #983 post) | NOT DONE — human step (below) |

## 6. What the human must do (handed to the principal)

`integrations/mmos/INSTALLED_ACCEPTANCE_SCRIPT.md` is the runbook:
1. **HUMAN: quit Mastermind OS** (Cmd-Q; pid at last observation 26675).
2. Run the one install command (script §2): `mmos_rollback.py --bundle
   ~/Applications/Mastermind OS.app install --from ~/.mastermind/mmos_bundles/mmos-v1-integration-20261109-29a82f77-29a82f779f3d--1bba0c01/Mastermind OS.app --execute`.
3. Launch; run the checklist (script §3, a–g) — honest expected states at
   this head, including Team roster UNAVAILABLE (wedged gateway socket,
   `LANE_HERMES_DIRECTOR_B2.md` — record, do not restart) and the honestly
   not-connected Code/Fleet-attempt surfaces.
4. Post-install receipt (must equal digest `sha256:1bba0c01…`,
   `embedded_marker`); optional rollback drill; paste evidence to #983.

## 7. Not done, and why

- **The install itself** — requires quitting the running app (human step;
  the tool refuses rc 4 while it runs, and this lane never passes
  `--execute`).
- **The user-path acceptance run + #983 post** — needs the installed app;
  this lane's constraint is preparation only.
- **No push/PR** — lane instruction (commit-only; integrator owns
  publication). No `src-tauri` source edits (build-only, as permitted); no
  `control_plane`, pins, `~/.hermes` changes; no secrets committed (client
  id deliberately referenced as `<public client id>` here, per the
  not-in-repo convention).
- Hermes gateway socket left wedged (recorded, not restarted) — out of
  scope for this lane; Team roster will honestly stay UNAVAILABLE until
  Hermes restarts it.

— Director I2, 2026-11-09.
