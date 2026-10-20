# Codex Switcher Business-member OAuth token guard

**2026-10-19 UTC / 2026-10-18 Pacific**. Status: **DRAFT SOURCE-ONLY**;
not installed, not deployed, no account changes.

## Problem proven on the actual existing code path

The M2 Codex Switcher stores six subscribed accounts, including four distinct
Personal Pro workspaces and two different Business members in one shared
workspace. The original source src-tauri/src/auth/storage.rs checked only
chatgpt_account_id (workspace) in sync_active_account_tokens. Synthetic
Business fixtures confirmed that an unrelated member's refreshed token could
overwrite the selected member's saved access/refresh tokens if their workspace
ID matched. RED: four targeted regression tests fail on original source; an
exact same-member control succeeded.

The other write path, update_account_chatgpt_tokens, directly replaced
saved tokens after an OAuth refresh response without member identity
verification. It bypassed the synchronization check. This source update
guards both paths. The native chatgpt_user_id ID-token field is compared
with the stored workspace, and account metadata/credentials are changed
ONLY after the workspace and member match. Business, Team and Enterprise
plans refuse missing or conflicting member claims. Personal Pro remains
compatible with legacy tokens lacking both member claims when the
subscription workspace still matches. Conflicting top-level and token
workspace identity refuses.

Only bounded claim structure was inspected for the current six installed
Switcher accounts. Both Business accounts have valid bounded member
claims in saved OAuth token metadata and different members in the same
workspace; the four Personal accounts have distinct workspaces. No emails,
raw IDs, account hashes or OAuth token bodies were emitted.

## Exact source carriage

Original local fork:
~/Documents/GitHub/codex-switcher-m2-20261011
at base 5f067ef615a6a4d1f80fe4fd79f086c0beac22c3
(the installed M2 Switcher remains separate and unchanged).

Isolated local source commit:
ef43d9e5734e5b2e2bf31cb808feb23bee141cd9
on mastermind/20261019-business-member-token-guard-sol-001.

Only source files modified:
- src-tauri/src/auth/storage.rs
- src-tauri/src/types.rs

No upstream Git remote was configured on this local Switcher repository.
The exact two-file git patch, SHA-256 pre/postimage manifest and
read-only replay verifier are instead preserved in the owning Mastermind
repository under ops/native_fabric/patches and
ops/native_fabric/verify_codex_switcher_business_member_source.py.
This is a review/transfer mechanism, NOT a new installer, identity store,
account selector, broker or retry plane.

## Tests and safety facts

- RED original: four Business ambiguity/cross-member tests failed
- GREEN target and full cargo test --offline source tree:
  **78 passed / 0 failed / 1 ignored** (ignored existing live-process
  inspection requiring explicit execution)
- Rust formatting checked for changed files only, since unrelated baseline
  src-tauri/src/auth/mod.rs formatting was deliberately not changed
- SHA replay of committed patch against exact original local source:
  EXACT_PREIMAGE_AND_POSTIMAGE_REPLAY=true;
  ORIGINAL_SOURCE_UNCHANGED=true
- Mastermind bundle static/failure regression tests: 5 passed
- Original installed Switcher app remained running and untouched, original
  account store was neither mutated nor overwritten, no device-login
  ceremony, account switch, refresh call, provider model turn or capacity
  claim performed.

This reduces cross-member credential confusion; it does not attest that
Business seats are Premium, prove an Executive worker is enrolled, or
authorize shared-subscription execution on a remote host.

## Release / rollback gate

Independent source and security review, hosted CI, then explicitly
authorized local app packaging/signing are required. At application
rollout, protect the already-active Switcher source store and token
refresh stream, ensure no Codex desktop/model session is interrupted,
and use the existing established app update and restart procedure.
Check actual B1/B2 switching and refresh path on each original account
with a real-app receipt, verifying that the known workspace remains the
same while member identity changes only on intentional account switch;
validate Personal Pro unchanged. On failure, restore the already
verified previous app build using the existing updater/backup procedure,
without blindly overwriting newer single-use OAuth refresh tokens.
A clean source build, PR review or CI green alone is NOT acceptance.

Neighboring source-only PRs retain their own owners:
#1365 six-seat selector, #1585 native observer, #1615 inert C4 worker
projection, #1618 native bounded worker message isolation. Do not install
or merge these together without resolving their exact control and
runtime-admission gates. This patch is independent of Executive
plugin backend_unavailable and does not retry or resolve it.


## October 20 local successor reconciliation — fail-closed unknown plans

An independent source review on PR #1630 identified an additional memberless
fallback: two missing user claims could rotate a matching-workspace token when
its plan was missing or a future unrecognized shared-workspace tier.
This could misclassify an unknown plan as legacy Personal; no production
cross-member token leak was observed.

The original local Switcher branch already held **a separate clean successor**
at `a744e4f8128db1074e91b4f18e16b445fab40af6`, committed 2026-10-19
20:04 PDT, based on original `ef43d9e5734e5b2e2bf31cb808feb23bee141cd9`.
The successor accepts memberless legacy rotation only when at least one
validated plan is a known Personal tier and every supplied plan is Personal.
Missing/unknown/shared plans fail closed. New Rust regressions prove no
credential rewrite across null/unknown plans or plan transition, including
both sync and direct refresh paths; known Personal behavior remains tested.
A legitimate `token_refresh.rs` test fixture now explicitly identifies Personal Pro.

The **same PR #1630** now carries the exact three-source patch (storage.rs,
token_refresh.rs, types.rs), anchored to the unchanged original local base
`5f067ef615a6a4d1f80fe4fd79f086c0beac22c3`, not a new PR or native app
installer. Digest-sealed manifest candidate SHA is `a744e4f...`; patch SHA-256
is `cd13b98008b66950f432f65cd2704e4626c573da39d90d3474d86de9cfdaddf7`.
The original two-file/78-pass candidate and related descriptions above are
**historical and superseded** by this bounded successor.

Observed verification on the M2 original source checkout:
- `cargo test --offline --locked -q`: **81 passed, 0 failed, 1 ignored**, exit 0;
- current-repo digest/replay verifier against the unchanged original checkout:
  `BUNDLE_DIGEST_VERIFIED=true`,
  `EXACT_PREIMAGE_AND_POSTIMAGE_REPLAY=true`,
  `ORIGINAL_SOURCE_UNCHANGED=true`, exit 0;
- five provider-free Mastermind bundle regression tests: **5 passed**, exit 0;
- original local source candidate worktree clean; installed Switcher app,
  protected credentials, active sessions and production capacity untouched.

Source validation does **not** replace independent new-head review, hosted CI,
approved Switcher packaging/signing, same-member real-app refresh and intentional
account-switch tests, or guarded rollback. The original root/outstanding gates
remain intact.
