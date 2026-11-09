# MERGE_MASTER_20261109 — Director M integration ledger

- **Branch**: `t3/merge-master-20261109` (from `t3/t3-hermes-restart-recovery` head `5df44144c`)
- **Merge commit**: `77abd220c` (plain `--no-ff`, two parents `5df44144c` + `77773d01a`; no rebase, no force, no squash)
- **Base**: `ff6d5ab67` · **Merged origin/master**: `77773d01a`
- **Merged master commits (12)**: `3652d8907` #2297 GitHub App plugin, `c4a6f298a` #2344 sign-in restore,
  `dd45d1112` #2363, `311619af6` #2362, `6696153d3` #2365 fabric pools, `9fa6c5b41` #2350,
  `494d09581` #2358, `b6e7d44c0` #2357, `6fc220a17` #2372 native T3 web client, `9e6659c4a` #1845,
  `28767babb` #2345, `77773d01a` #2342 live Slack gateway.
- **Scope note**: the briefing listed ten commits ending at `28767babb`; `git fetch origin master`
  at execution time brought one additional commit `77773d01a` (#2342, source-version live Slack
  gateway, resume and safe role handoffs). It adds only three new files
  (`docs/runbooks/hermes-shared-slack-gateway.md`, `integrations/hermes_runtime/slack_gateway.py`,
  `integrations/hermes_secretary/tests/test_slack_gateway.py`), so it merged additively and could
  not conflict; its new suite was run anyway (see Verification).
- **No push, no PR.** Local commits only, on the assigned worktree.

## Conflicted files and resolution

`git merge --no-ff origin/master` reported exactly **2 conflicts**; the four predicted
frontend/Rust source files auto-merged and were verified for both sides' intent.

| File | Conflict | Resolution |
|---|---|---|
| `tests/executive_fabric_release_identity_review.py` | `REVIEWED_FILES['app/mastermind_os/src-tauri/src/auth.rs']` pin moved by both sides (ours: #2351 +30 lines → `ace408ab…` @3769/3774/3778; master: #2344 primary/work-entry rewrite → `6ce90063…` @3782/3787/3791) | Recomputed the **merged** auth.rs: pin → sha256 `612e97c9…` with the same three `503` fixture operands at 3812/3817/3821 (byte-identical tokens and columns; see Pin moves). Master's `autonomy_control.py` and `authorization_continuation.rs` pin entries carried through as master's bytes (our side never touched those sources). |
| `tests/test_discovery_correction_identity_review.py` | Same `auth.rs` RECORDS entry moved by both sides | Same recomputed values; asserts equality with `REVIEWED_FILES`, so both registries now agree on `612e97c9…`. Master's `authorization_continuation.rs` entry (sha `71b76671…` @542/543) carried through. |

### Auto-merged files — both-sides intent verification

- `app/mastermind_os/src/App.tsx` — master's #2344 sign-in semantics kept exactly
  (`authenticationButtonRef`, `existingAuthenticationControl`, `NativePrimaryAccountControl`
  wrapper, `NativeWorkAuthorizationControl`, `nativeAuthFeedback` paths); our additive routes kept
  (Team/Code in `navigation`/`primaryNavigation`/icons/labels/quietHeader, `TeamRoute` with
  `HermesNativePanel`, `CodeWorkspace`, `ProjectDeliveryPanel` team-delivery details,
  `CapacityFabricRead`). Typecheck + full vitest run prove composition.
- `app/mastermind_os/src/host.ts` — master's `signInPrimary`/`readWorkAuthorization`/`signInForWork`
  client methods, pending/uncertain guards and `primaryAccount`/`workAuthorization` host bindings;
  our `readCapacityFabric` binding/native read. No overlap in hunks.
- `app/mastermind_os/src-tauri/src/auth.rs` — master's `SignInIntent` split (`LegacyFull` /
  `PrimaryAccount`), `transaction_for`, `PRIMARY_AUTH_SCOPE_REFUSED`, primary-account expiry
  refusal, `pub mod primary_account; pub mod work_authorization;`; our `read_capacity_fabric`
  command inserted in the model-configuration region. Disjoint regions; whole-file hash re-pinned.
- `app/mastermind_os/src-tauri/src/main.rs` — master's three new invoke commands after
  `auth::sign_in`; our `MM_RECEIPT_MARKER`/`install_marker` and `read_capacity_fabric`
  registration. Disjoint hunks.

### Protected files — untouched by the merge

`git log ff6d5ab67..origin/master -- control_plane/executive_runtime.py
config/executive_worker_routes.json control_plane/t3_execution_adapter.py` is **empty**: master
changed none of them, so the merge resolved them to our side byte-for-byte with no conflict and no
edit. No blocker arises. `control_plane/t3_execution_adapter.py` remains exactly Director A3's
version (`git diff HEAD^1..HEAD` shows no delta for it beyond the merge's own none).

## Pin moves requiring distinct CRITICAL review

All moved pins go to the exact new reviewed bytes/sites of the same reviewed tokens; the
source-changing commit is named at each pin. No pin was deleted, skipped, xfailed or widened.
A whole-registry sweep (every entry of `REVIEWED_FILES` and `INCIDENT_REVIEWED_FILES`, hashed
against the merged tree) reports **0 stale pins**.

1. `tests/executive_fabric_release_identity_review.py` `REVIEWED_FILES`:
   - `app/mastermind_os/src-tauri/src/auth.rs` → sha256
     `612e97c934d4407c3b08bdf3c15bf75e8df5a1507d4161435b862896acff4737`; sites
     `((3812,68,71),(3817,69,72),(3821,67,70))` all `'int','503'`. Source commits: master `c4a6f298a`
     (#2344 primary/work-entry rewrite, base→master moved the operands to 3782/3787/3791) composed
     with our `3838b8b82` (#2351 capacity-fabric read, +30 lines above the fixture) — the merge
     composes both shifts. Old pins: ours `ace408ab…` @3769/3774/3778, master's `6ce90063…`
     @3782/3787/3791; pre-#2351 base pin `6592b76e…` @3739/3744/3748.
   - `integrations/hermes_attended_fabric/native.py` → sha256
     `7b6d14ea2e041f98573627925340f00c4b6e6c3cfde5a16e297aa3a52079a0bf`; sites
     `((57,65,68),(280,60,63))` both `'int','500'` (same escalation-reason length limits).
     Source commit: master `6696153d3` (#2365 manual pool enrollment, +9 lines above both sites).
     **Master shipped this composition without moving its own pin** — origin/master itself fails
     `tests/test_executive_reviewed_site_identity_tokens.py` for this path (pin still
     `9b26d8e1…` @48/271 = the pre-#2365 blob). Moved here at merge time so the protected
     identity suite is green on the integration branch; needs the same distinct CRITICAL review
     as every other row (the dated comment in the pin file records this provenance).
2. `tests/test_discovery_correction_identity_review.py`: `auth.rs` RECORDS sha + sites exactly as
   in (1) (the test asserts registry equality, so the two files cannot drift).

Everything else in the merged registries — including our side's #2351 pin moves
(`paid_fabric_backend.py`, `app.py`, `workspace_read_service.py`, new
`workspace_capacity_fabric.py` / `capacity-fabric.css` pins) and master's #2344 moves
(`autonomy_control.py` @`e8c812d6…` 7008/7009/7889/8689/10104, `authorization_continuation.rs`
@`71b76671…` 542/543) — required no further move: each side's pinned sources were untouched by
the other side.

## #2372 relationship: `integrations/session_bridge/t3_web_client.py` vs our `control_plane/t3_execution_adapter.py`

Master's #2372 lands a **stateless presentation client** over the installed `t3` host CLI
(`T3CliClient.launch/send/read/list_threads`, `HandoffBrief` compiler, `ThreadReceipt`,
`NativeEffectUnknown`). Relationship to our Executive-admitted adapter:

- **Executive admission**: `t3_web_client.py` contains no admission path at all — zero references
  to Executive/admission/fabric; it launches no subprocess itself ("This class neither launches
  subprocesses itself nor supplies/borrows credentials. The existing authorized host owns
  execution."). The caller must inject an authorized absolute executable path and a runner. No
  production module imports `T3CliClient`/`HandoffBrief` (only its two test files); the doc marks
  it "implementation in progress". So it does **not** add a second worker lane or bypass
  Executive admission today — it is an unwired library for ChatGPT-Web handoffs whose authorization
  burden sits on whatever future caller injects the runner.
- **Idempotency identity**: it does **not** share the `clientRequestId` identity. There is no
  `clientRequestId` anywhere in it or its tests; `launch` shells `t3 thread start --title …
  [--worktree … --branch …] <project> -` with no retry key, and any modifying-call failure raises
  `NativeEffectUnknown` ("Retain original dispatch/host/process. Never retry or change carrier.")
  with reconciliation-at-original-thread semantics. Our `T3ExecutionAdapter` derives
  `clientRequestId` deterministically from the broker `ExecutionBinding` (child identity triple +
  request_digest + adapter_id), persists intents/receipts in its SQLite sibling store
  (intent-before-launch, receipt-before-ACK), and qualifies the namespace by authenticated
  principal — the live-proof finding that the same `clientRequestId` under two OAuth clients minted
  two different threads is exactly why identity is principal-qualified there. The two clients
  share no state, store, or identity plane.
- **Upstream retry-key claim** — `docs/T3_WEB_COLLABORATION.md` (line 17), quoted verbatim:
  > "Version qualification matters: PR #2356's pinned native launch accepted `clientRequestId`; current upstream documentation says launch has no retry key. Never assume exactly-once launch across versions or OAuth clients. After unknown launch/send effects, reconcile the original process/thread; do not repeat, change identity, or launch on another carrier."

  This is consistent with our adapter's persisted-intent design: where the key exists it is derived
  and persisted; where it does not (current upstream CLI surface, per master's census), the only
  lawful failure mode is reconcile-the-original, which both modules implement.
- **No rewiring performed**: the merge takes #2372's four files byte-for-byte (doc + client + two
  test files, all new); nothing in our tree was repointed at it and it was not deleted.

## Verification (exact commands and counts)

Python (worktree root, `env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q`):

- **Union list, one session: 886 passed, 30 skipped, 2 xfailed, 0 failed (exit 0; 918 outcomes).**
  The machine was under external load (load average 76–113 from other tenants) the whole time;
  no Python flake was observed.
- Master-diff test list `git diff --name-only ff6d5ab67 origin/master -- tests/` (25 files) +
  the 8 identity/pin files + the 12 named Rev5/team/quota/hermes files, deduplicated to 29 files
  (list in `/tmp/merge_master_tests_final.txt`), run as one session.
- Extra, beyond the briefed list: `integrations/hermes_secretary/tests/test_slack_gateway.py`
  (new from post-briefing #2342) — **29 passed, 0 failed**.
- Targeted pre-commit pin checks: `tests/test_discovery_correction_identity_review.py` +
  `tests/executive_fabric_release_identity_review.py` +
  `tests/test_executive_reviewed_site_identity_tokens.py` → **186 passed**;
  `tests/test_workspace_fabric_review_pins.py` `tests/test_workspace_control_room_review_pins.py`
  `tests/test_next_mounted_identity_pins.py` `tests/test_company_consultation_identity_review.py`
  `tests/test_ceo_submit_armed_composition.py` → **242 passed**.

Frontend (`app/mastermind_os`, local `node_modules`):

- `npm ci` → exit 0.
- `npm run typecheck` (`tsc -b --pretty false`) → exit 0, no errors.
- `node_modules/.bin/vitest run --maxWorkers=2` → **7143 passed | 13 failed | 12 skipped
  (7168 tests, 433 files)**; all 13 failures classified as **load flakes, not regressions**
  (isolation rerun detail below).
  - Note: a first attempt via `npx vitest run` resolved vitest from the npx package cache
    (`/Volumes/Mastermind/agent-workspaces/cache/npm/_npx/…`) which cannot resolve `jsdom`;
    60 jsdom-environment files failed collection with `ERR_MODULE_NOT_FOUND` while all 3822
    collected tests passed. Rerun with the project-local binary (vitest 5.0.1, jsdom ^30.1.0
    both installed by `npm ci`) is the authoritative result above. Tooling artifact, not a merge
    regression.
  - **Flake/regression split (mission-required isolation rerun).** The host ran at load average
    76–113 (external tenants) during the full run; every one of the 13 failures was a 3.6–5.4 s
    timeout at the 5 s `testTimeout` ceiling, in the three heaviest App integration files:
    `src/App.mission-result.test.tsx` (5), `src/App.test.tsx` (7, master's #2344 rewrite of that
    file), `src/App.operation-reopen.test.tsx` (1). Rerun of exactly those three files in
    isolation (`--maxWorkers=2`, load ≈56): **165 passed, 2 skipped, 1 failed** — mission-result
    and App.test fully green. The one remaining (`operation-reopen` "local busy after selection
    invalidation … blocks Launch…") **passes when run solo** (`-t` filter, `--maxWorkers=1`,
    exit 0). Verdict: 13/13 flakes from machine contention; 0 merge regressions.
- `npx vite build` (from `app/mastermind_os`) → exit 0, `✓ built in 5.49s` (pre-existing
  chunk-size/dynamic-import warnings only).

Rust:

- `MM_SOURCE_REVISION=77abd220c… MM_BUILD_IDENTITY=merge-local MM_NATIVE_REFRESH_ENABLED=1 cargo
  test --locked --all-targets --manifest-path app/mastermind_os/src-tauri/Cargo.toml` →
  **exit 0; 3 suites; 306 passed, 0 failed, 8 ignored** (MM_SOURCE_REVISION was the merge commit
  sha at run time; the ledger commit follows the merge).

## Left red / not done

- **Nothing left red.** Python union list 886/0; pin registries 0 stale (full sweep);
  frontend typecheck 0 errors, vitest 7143 passed with 13 load-flakes all proven passing in
  isolation/solo, `vite build` exit 0; cargo 306/0.
- Not done / out of scope by assignment: no push, no PR, no CI observer armed, no changes to
  `control_plane/executive_runtime.py`, `config/executive_worker_routes.json` or
  `control_plane/t3_execution_adapter.py` (all byte-identical to our pre-merge side; master
  touched none of them).
- One pre-existing master defect surfaced and repaired by pin move, needs the distinct CRITICAL
  review: master #2365 changed `integrations/hermes_attended_fabric/native.py` without moving its
  pin — origin/master is itself red on `test_executive_reviewed_site_identity_tokens` for that
  path (see Pin moves §1). Recommend the release lane also fix that pin on protected master.
- d8 identity scan: this merge's own edits add no identity literals (service-account names) to
  docstrings — the only authored text is dated pin-move comments citing PR numbers/commit shas,
  same form as the incumbent rows.
