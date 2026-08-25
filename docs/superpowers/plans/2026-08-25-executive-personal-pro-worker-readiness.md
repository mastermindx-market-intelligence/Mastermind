# Executive Personal Pro Worker Readiness — Implementation Plan

> Current-source continuation for Chairman-approved three-account Codex worker isolation.

**Date:** 2026-08-25  
**Repository:** `mastermindx-market-intelligence/Mastermind`  
**Protected pickup:** `51f9942733b86e550bb9169d2a43462bd28e774f`  
**Branch:** `codex/executive-personal-pro-worker-readiness-20260825`  
**Worktree:** `/Users/chriswong/Documents/Cluade/Mastermind-phase1g-w6-personal-pro-20260825`  
**Operation key:** `EXEC-PERSONAL-PRO-WORKER-READINESS-20260825`  

## Observable mission

Make the existing Executive OS host/auth readiness plane capable of provisioning and independently attesting exactly three already-owned ChatGPT Personal Pro Codex worker accounts as three isolated native worker realms, without touching the normal Mac Codex app or weakening the existing company-workspace worker policy.

The independently useful capability delivered by this slice is:

```text
codex-pro-01 -> _mastermind_codex_01 -> dedicated CODEX_HOME -> its own readiness receipt
codex-pro-02 -> _mastermind_codex_02 -> dedicated CODEX_HOME -> its own readiness receipt
codex-pro-03 -> _mastermind_codex_03 -> dedicated CODEX_HOME -> its own readiness receipt
```

Each realm can be bootstrapped, device-authorized, verified, invalidated, and requalified without opening, copying, replacing, or selecting another realm's credential file.

## Why this is the current-source carrier

Historical Phase 1G PR #66 and its #68–#71 dependency topology were explicitly closed as `SUPERSEDED_BY_CURRENT_EXECUTIVE_AND_PROVIDER_ARCHITECTURE`. They are archaeology, not current authority. This slice does not recreate their provider-capacity database or router.

Current boundaries remain:

- Macro Shared AI Provider Control owns provider/account capacity observations and produces the strict secret-free Capacity Fabric projection.
- Mastermind model routing owns task/model suitability, not quota truth.
- Executive OS owns Job, Attempt, Worker, Event and final atomic placement.
- The worker harness owns native session and provider-home mechanics.
- Agent OS and Control Room remain durable records/projections, not dispatch or quota authority.

CF1 PR #6297 is separately parked `DRAFT / HOLD-FOR-SOL`; this auth-isolation slice neither consumes nor releases it.

## Verified current state

- Protected Mastermind `master`: `51f9942733b86e550bb9169d2a43462bd28e774f`.
- The dirty primary checkout is not used.
- Current host has `_mastermind_exec` UID/GID 450 and `_mastermind_worker` UID/GID 451.
- `_mastermind_ops` owns GID 453.
- UIDs 454, 455, and 456 are currently unowned.
- Canonical `/var/db/mastermind-executive/workers/codex-01/provider-home`, its `auth.json`, and the legacy provider-readiness receipt are absent on the inspected Mac.
- Existing readiness is hard-coded to one worker, one provider home, one receipt, and the company-workspace binding class.
- Existing policy deliberately rejects `planType=pro`.
- The existing Multilogin/Chairman-seat harness is merged, but this slice does not automate or inspect a Chairman seat.

## Frozen realm inventory

The public reviewed inventory contains logical host mechanics only—never provider account IDs, emails, profile IDs, OAuth codes, tokens, cookies, or private URLs.

| Slot | Worker principal | UID | Primary group | Provider home | OAuth seat reference | Policy |
|---|---|---:|---|---|---|---|
| `codex-01` | `_mastermind_worker` | 451 | `_mastermind_worker` / 451 | `/var/db/mastermind-executive/workers/codex-01/provider-home` | none | existing company realm |
| `codex-pro-01` | `_mastermind_codex_01` | 454 | `_mastermind_worker` / 451 | `/var/db/mastermind-executive/workers/codex-pro-01/provider-home` | `chatgpt1` | Personal Pro device OAuth |
| `codex-pro-02` | `_mastermind_codex_02` | 455 | `_mastermind_worker` / 451 | `/var/db/mastermind-executive/workers/codex-pro-02/provider-home` | `chatgpt2` | Personal Pro device OAuth |
| `codex-pro-03` | `_mastermind_codex_03` | 456 | `_mastermind_worker` / 451 | `/var/db/mastermind-executive/workers/codex-pro-03/provider-home` | `chatgpt3` | Personal Pro device OAuth |

The Personal Pro principals share only the reviewed artifact group. Unique UIDs, mode-0700 provider homes, exact worker-owned mode-0600 single-link `auth.json` files, clean environment construction, per-UID process sweeps, and per-slot readiness receipts form the isolation boundary.

## Policy law

Do not add `pro` to the company plan allowlist.

Two closed policies coexist in one canonical readiness implementation:

1. `company-workspace-admin-attested`
   - preserves all current accepted company plan values;
   - preserves current reviewed credential kinds and auth-mode binding;
   - rejects Personal Pro.
2. `personal-pro-dedicated-worker-attested`
   - requires `expected_credential_kind=device-auth`;
   - requires exact Codex auth mode `chatgpt`;
   - requires `account.type=chatgpt` and exact `planType=pro`;
   - rejects company plans, Plus, free, future/unknown plan values, access tokens, service accounts, and forced workspace selection.

The probe emits only the existing sanitized identity fields. Account IDs, emails, workspace IDs and raw App Server frames remain forbidden.

## OAuth isolation law

- `CODEX_HOME` and `HOME` are both the selected provider home.
- Working directory is the selected provider home, never an operator checkout.
- Auth store is session-forced to `file` and forced login/workspace config remains forbidden.
- Normal `/Users/chriswong/.codex`, the Codex desktop app, its browser session and its Keychain state are never read, written, logged out, or selected.
- Device OAuth is run as the selected disabled worker principal only.
- Initial interactive authorization names the logical Multilogin seat reference, but code does not open, start, inspect, click, type into, or mutate that profile.
- A missing or existing credential is handled only inside the selected provider home. Rotation still requires explicit `--replace-existing`.
- No account credential is copied or swapped between slots.

## Scope

1. Add one strict, secret-free provider-worker slot catalog.
2. Centralize identity policy so the live probe and readiness validator cannot drift.
3. Parameterize identity and inference probes by a validated slot descriptor while preserving the legacy company defaults.
4. Make the auth provisioner accept one allowlisted `--slot-id`, derive every identity/path from the catalog, and create/reuse the selected slot's receipt only.
5. Extend host bootstrap to create the three disabled worker principals and their mode-0700 provider-home/state directories idempotently.
6. Add a sanitized slot-status command and operator documentation.
7. Add discriminating tests for cross-slot credential/receipt/path/process confusion and normal-Mac exclusion.

## Explicit non-goals

- No credential enrollment or OAuth ceremony from an unmerged branch.
- No reading or returning credential contents.
- No automated password, passkey, OTP, CAPTCHA, browser click/type, cookie, storage or account switching.
- No Multilogin profile start/stop/mutation in this slice.
- No normal Mac Codex logout, login, account switch, `~/.codex` access, or desktop-app automation.
- No CF1 merge/release, CF2 consumer, quota observation, placement, routing, failover, Job claim, worker LaunchDaemon fan-out, VPS deployment, Slack, Wake, MCP write, plugin installation, or subagent execution.
- No Alibaba, GLM, Claude or OpenRouter adapter in this slice.
- No resurrection of PR #66 or a duplicate provider-capacity/state plane.

## Failure and correction states

- Unknown slot, duplicate slot identity, reused UID, reused provider home, reused readiness path, invalid seat mapping, wrong binding class, wrong auth mode or wrong plan refuses.
- Existing user/group/home metadata must match exactly; bootstrap never silently repairs an ambiguous identity.
- Any symlink, ACL, wrong owner, wrong mode, extra hard link, empty auth file, process still alive during recovery, stale receipt, changed auth inode or changed binary fails closed.
- A credential in another slot does not count as present for the selected slot.
- A readiness receipt from another slot cannot be reused for the selected slot.
- `--replace-existing` applies only to the selected slot.
- Interrupted readiness retains the existing bounded transaction/recovery law.
- Later catalog changes invalidate exact-source review and require requalification.

## TDD implementation sequence

### Task 1 — strict catalog and shared policy

Files:

- add `ops/executive_os/provider_worker_slots.py`
- add `ops/executive_os/provider_identity_policy.py`
- add `tests/test_provider_worker_slots.py`
- update `tests/test_provider_identity_readiness.py`

Start with failing tests for exact four-slot inventory, unique identities/paths, plan/auth/binding matrices, identifier-free rendering, and unknown-slot refusal. Then implement the smallest catalog and pure policy.

### Task 2 — parameterize provider identity/readiness

Files:

- modify `ops/executive_os/provider_identity_probe.py`
- modify `ops/executive_os/provider_readiness.py`
- modify `tests/test_provider_identity_readiness.py`

Start with failing tests proving Personal Pro passes only under its dedicated device-auth policy; the company path still rejects Pro; wrong UID/GID and a receipt copied across slots refuse.

### Task 3 — parameterize the inference canary

Files:

- modify `ops/executive_os/provider_inference_canary.py`
- modify `ops/executive_os/provider-inference-canary.sh`
- modify `tests/test_executive_provider_inference_canary.py`

Start with failing tests proving the selected slot controls user/group/UID/GID/provider home, arbitrary path overrides remain forbidden, and one slot's invocation contains no other slot path.

### Task 4 — exact-slot auth coordinator

Files:

- modify `ops/executive_os/provision-worker-auth.sh`
- modify `tests/test_executive_worker_auth_provisioner.py`

Start with source/adversarial tests proving an allowlisted slot is mandatory for Personal Pro, all low-level values are catalog-derived, normal `~/.codex` is absent, receipt paths are per-slot, and rotation cannot target a different slot.

### Task 5 — idempotent host bootstrap

Files:

- modify `ops/executive_os/bootstrap-host.sh`
- modify `tests/test_executive_launchd_config.py`

Start with tests for exact UIDs 454–456, shared artifact GID 451, four exact primary worker-group members, three mode-0700 provider homes, and no service start or credential copy.

### Task 6 — sanitized operator journey

Files:

- add `ops/executive_os/provider-slot-status.py`
- update `ops/executive_os/HOST_PREREQUISITES.md`
- add/update focused tests

The status output may report only slot ID, logical seat reference, filesystem presence booleans, metadata-valid booleans, readiness state/refusal code, and whether a worker process is present. It must not emit credential bytes, account identity, profile ID, private URL or arbitrary path.

### Task 7 — proof and return

Run:

```text
python -m pytest -q \
  tests/test_provider_worker_slots.py \
  tests/test_provider_identity_readiness.py \
  tests/test_executive_provider_inference_canary.py \
  tests/test_executive_worker_auth_provisioner.py \
  tests/test_executive_launchd_config.py

python -m pytest -q tests/test_executive_codex_worker.py tests/test_executive_worker_broker.py
python -m compileall -q ops/executive_os
git diff --check
```

Then run the repository's required CI-equivalent command, inspect the exact diff against protected pickup, perform Sol `REVIEW_RETURN`, and use a draft PR until hosted proof completes.

## Merge and live-proof meaning

Merge would make the three Personal Pro worker realms safely expressible, bootstrap-able, enrollable and independently readiness-attestable. It would not make any account authenticated, ready, running, routed, quota-aware or autonomous.

After an accepted merge, live host proof is a separate exact-release operation:

1. bootstrap/verify all three disabled principals and homes;
2. perform one device OAuth ceremony per slot using the named Multilogin seat, without touching the normal Mac app;
3. run one sanitized identity/readiness canary per slot;
4. prove three distinct auth-file identities and three current passing receipts without reading their contents;
5. stop and return before worker service fan-out or placement.

## Stop condition

Stop this carrier when exact-head tests and review prove the three independent Personal Pro readiness realms and the company compatibility path. Do not absorb capacity ingestion, router placement, worker LaunchDaemon fan-out, session spawning, MCP/plugin composition or failover. Those are separate current-source continuations.
