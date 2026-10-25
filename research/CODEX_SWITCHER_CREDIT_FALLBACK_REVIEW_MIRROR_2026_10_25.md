# M2 Codex Switcher credit fallback - independent review mirror

**REVIEW EVIDENCE ONLY - NOT IMPLEMENTATION OWNER OR DEPLOYMENT AUTHORITY.**

Canonical source commit 10a1b9af293e6f4f4da20529e2dde9d1192a3525 and review-only local packet commit f8a48f4e8b281c587d05d3777baddca5b67ed791 (direct child).

This GitHub-hosted review copy does not claim source was pushed, installed, reviewed, verified live, or accepted. No cookies, private credentials, tokens or auth stores included.

The changed-file source patch SHA256 is 8e0d04c287578ed569f810d51375c56343be602dc620126677452af48cf29f8f verified from local Git. The staged release helper is not approved for use until independent review and session-safety acceptance.

## Included review materials

### Assignment and full review scope - README.md

SHA256: 50ea9398d88963da65d9a2c005df006d06dadbe3e34a6db5c94a3605f702a168

~~~markdown
# Independent review packet — M2 Codex Switcher paid-credit fallback

**Status: REVIEW REQUEST, NOT APPROVAL.** This directory is part of a new, documentation-only Git worktree and is intentionally separate from the unchanged implementation branch. A different, genuinely independent reviewer should inspect the code and local release helper and return concrete severity-ranked findings. No installation, credential refresh, account switch, quota-reset POST, or paid-credit spending is authorized by this packet.

## Immutable review subject

| Item | Exact identity |
|---|---|
| Product | Codex Switcher, M2 Studio installed app |
| Implementation candidate SHA | `10a1b9af293e6f4f4da20529e2dde9d1192a3525` |
| Parent/base SHA | `a744e4f8128db1074e91b4f18e16b445fab40af6` |
| Changed implementation file | `src-tauri/src/tray.rs` |
| Candidate changed-file diff | `candidate-10a1b9af.patch` |
| Diff SHA256 | `8e0d04c287578ed569f810d51375c56343be602dc620126677452af48cf29f8f` |
| Original candidate branch | `mastermind/m2-paid-credit-fallback-20261023` |
| Review-packet-only branch | `mastermind/credit-review-packet-20261024` |
| Original local checkout (M2) | `~/agent-workspaces/codex-switcher-m2-paid-credit-fallback-20261023` |
| This review worktree (M2) | `~/agent-workspaces/codex-switcher-independent-review-20261024` |
| Original M1 read-only review input | `~/lanes/codex-switcher-review-20261024-03/review-src/` (if M1 accessible) |

**Critical SHA distinction:** the commit containing this packet is a **later documentation commit**, NOT the implementation to be reviewed. Inspect the exact implementation object using `git show 10a1b9af293e6f4f4da20529e2dde9d1192a3525:src-tauri/src/tray.rs`. The original implementation worktree was clean at this SHA during the October 24 census; no source rebuild is needed just because this packet was committed.

The local repository currently has **no configured Git remote**. This packet is a local Git commit on the M2, not a claimed GitHub publication. A fresh authorized session can open this M2 worktree via Desktop Commander and inspect the exact immutable commits. If a remote is later configured under normal source-custody procedures, reconcile it before publishing; do not add an invented remote.

## User-requested behavior and falsifiers

**Job:** As soon as every eligible, non-masked account has **strictly below 5%** remaining included usage, select the account with the highest spendable **paid credits**. If the active account itself holds the largest balance, continue on that account; after credits empty, select the next-highest account with a positive balance. When included usage is available again, preserve normal allowance-based switching rather than needlessly spending paid balance.

Review against all of these cases; passing the existing tests does not prove correctness:

1. Effective quota uses the restrictive valid usage window, not a convenient window. Exactly 5% is **not** below 5%. Missing, failed, or stale readings must not be silently converted to zero.
2. Each eligible account is considered exactly once, including Personal Pro and eligible Business accounts, with masked records excluded. The active-account identity must remain stable across asynchronous usage fetch and final selection.
3. Paid spendable credit balance is NOT promotional quota-reset credit. Balance type/format, `has_credits`, `unlimited_credits`, negative/invalid/unknown values, ties, and zero credits need safe semantics.
4. If active paid credit balance is depleted and another is positive, the next-highest account must actually be selectable; do not get stuck behind the ordinary 1% trigger or choose a candidate with more included quota but no spendable credits.
5. Existing allowance auto-rotation policy (M2 configured normal trigger: 1%), `Preserve Resets` and `Concentrate Burn` modes, pause/cooldown, uncertain reset-prevention, and eligible option selection must remain coherent.
6. No protected active Codex session is terminated, orphaned, or silently rebound. Verify the final pre-switch re-read is still valid at the moment of effects; challenge TOCTOU, stale paid balances, and a newly recovered quota.
7. The existing Business-member token isolation in the base commit is preserved. No cross-account refresh-token rewrite or user-visible account identity mixup.
8. No independent reviewer creates code changes or grants live production permission as part of review. A PASS is **source-level**, not proof of natural 5% credit switching on production.

## Source and documents included

This Git branch includes the complete existing Codex Switcher source at the immutable candidate ancestry. Start with:

- `src-tauri/src/tray.rs` — credit candidate selector, decision, async revalidation, tests
- `src-tauri/src/types.rs` — `UsageInfo`, account eligibility structures
- `src-tauri/src/api/usage.rs` — real `rate_limits`, `credits.balance`, and usage ingestion
- `src-tauri/src/auth/storage.rs` — persisted account / policy and auth guards
- `src-tauri/src/commands/account.rs` and `process.rs` — actual switch and session safety
- `src-tauri/src/commands/account_stats.rs`, `src-tauri/src/commands/mod.rs`
- `review_packets/m2-paid-credit-20261024/candidate-10a1b9af.patch` — exact source delta

Review the deployment consumer as an **additional, separate file set**:

- `guarded_release.py` — copied SHA256 `d462da91678736e472784d1f76871360c2237fb8ccc6dbce8c5b4a2f5246604c`
- `test_guarded_release.py` — copied SHA256 `ef647f7fc3e464b279d5f3435f72029658a21f7e234d98ce1f5ced62df95ad38`
- `RELEASE_RUNBOOK.md` — copied SHA256 `ab8fa5a7e432416ce45795a0c570a9cb125473c8291cc045e778e171a4bc5870`

These **review copies** are only in this packet commit; production release originals remain on the M2 at `~/agent-workspaces/codex-switcher-paid-credit-release-20261024/`. The helper's real production install branch has never executed; its guard and rollback fixtures passed but this is not deployment acceptance. Review for rollback under process-launch failure, post-swap authentication drift, unsafe reruns, race windows, and accurate receipt semantics.

## Tool-evidence ledger (not external review)

- Rust: `cargo test --offline --locked --all-targets -q` returned **86 passed, 1 pre-existing ignored**, zero failures. Relevant M2 evidence: `/tmp/mmx_codex_credit_fulltargets_20261024.log`.
- Frontend: `pnpm test:desktop-reopen` **7 passed**, `pnpm test:close-preference` **3 passed**, `pnpm test:reset-credits` **3 passed**; total **13 passed**. Relevant M2 evidence: `/tmp/mmx_codex_credit_frontendtests_20261024.log`.
- Release helper: local syntax, read-only preflight and verify succeeded; no-approved-review install intentionally refused before effects. Two additional hermetic fixture tests passed (synthetic success backup/swap/receipt; synthetic launch-failure rollback). The helper and fixture run are NOT independent release review.
- Packaged macOS arm64 executable signed locally, SHA256 **`e0c615f92a5975e313e25e7454002000a61da107530e421f64c6751e0ea2b9cb`**.
- Installed M2 executable still old signed binary, SHA256 **`edc5260ff8272d7928d2db5f2988346bf4d388643febc0a8c2ee326790716aec`**. Verified PID 1469 at census; live sessions present (previous preflight saw 46 Codex-related processes). No app replacement.
- User account/auth stores have NOT been copied into this packet. Do not access or disclose their contents to perform the review.

## Fabric admission record — why this packet exists

| Operation | Requested avenue | Canonical observation |
|---|---|---|
| `...-05` | GLM | `REQUEST_REFUSED_BEFORE_LAUNCH`, no eligible host |
| `m2-switcher-paid-credit-review-20261024-06` | MiniMax, `subject_pool=openai` | Native rc75: `NONE reason=pool minimax has no eligible mode on requested host`; status `REQUEST_REFUSED_BEFORE_LAUNCH` |
| `m2-switcher-paid-credit-review-20261024-07` | Grok picker / Cursor-backed route, `subject_pool=openai` | Request entered native carrier but **actual executor selected Qwen 3.8 Max** and returned provider HTTP 429, terminal `rc=1`, no reviewer result |

The builder was an attended OpenAI ChatGPT session; `subject_pool=openai` describes author identity, NOT reviewer identity. The native picker advertised `cursor-grok-4.6-high`, but the actual `-07` execution receipt named Qwen. Do **not** claim this was a Grok review or replay failed operations. These receipts are capacity/transport evidence, never source review acceptance.

## Exact independent-review procedure

1. Read the candidate and packet from this repo; verify the Git candidate/base identities and file hashes. Compare `git show --format= 10a1b9af293e6f4f4da20529e2dde9d1192a3525 -- src-tauri/src/tray.rs` to `candidate-10a1b9af.patch` byte-for-byte.
2. Independently inspect the code paths above, construct specific counterexamples, and assess whether the user's 5% and next-highest-credit intent is actually met. Include negative/unknown/Business account cases and session protection.
3. Review `guarded_release.py` and `RELEASE_RUNBOOK.md` for safe release semantics. Note separately whether external-source review could be accepted as a reviewer receipt and how authorized release tooling would consume it; do not invent Fabric acceptance.
4. Deliver a **standalone** written verdict `DISPOSITION: PASS | CONDITIONAL | FAIL | UNVERIFIABLE`, along with your independent reviewer identity/mode, the exact candidate SHA, severity-ranked findings, file/line locations, counterexamples, source limitations, and remaining production tests. If blocked, name exact missing evidence.
5. The source owner adjudicates findings and performs repairs. Changing source HEAD requires rerunning relevant tests/build and a fresh independent review. Installing the app requires its own approved guarded release and naturally quiescent Codex sessions; a reviewer never deploys.

No one should mistake committing this packet, green Rust tests, a transport receipt, or a reviewer summary for a real paid-credit switching proof.
~~~

### Evidence and test results - EVIDENCE.md

SHA256: 0b3a791e7fcdaf6ce968dd10bb9d46eb65b34cd51114af510190f094f4e088bf

~~~markdown
# Exact-candidate evidence summary (not independent review)

Observed against Codex Switcher source commit `10a1b9af293e6f4f4da20529e2dde9d1192a3525`. Evidence gathered by the initiating operator on M2; an independent reviewer must validate substantive behavior separately.

## Compiled and tested code

Command: `cd src-tauri && cargo test --offline --locked --all-targets -q`

Captured M2 local log: `/tmp/mmx_codex_credit_fulltargets_20261024.log`

```text
test result: ok. 86 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.01s
test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
ALL_TARGETS_RC=0 (from tool process exit)
```

Commands: `pnpm test:desktop-reopen`, `pnpm test:close-preference`, `pnpm test:reset-credits`

Captured M2 local log: `/tmp/mmx_codex_credit_frontendtests_20261024.log`

```text
== test:desktop-reopen ==
tests 7; pass 7; fail 0
== test:close-preference ==
tests 3; pass 3; fail 0
== test:reset-credits ==
tests 3; pass 3; fail 0
FRONTEND_TESTS_RC=0 (from tool process exit)
```

Total feature/regression: **99 passing tests, one ignored** (86 Rust + 13 frontend). The skipped Rust test was pre-existing. Source has not changed since these runs.

## Guarded release helper

The separate, copied `test_guarded_release.py` on M2 ran in temporary fixture directories and returned:

```text
test_hermetic_install_swap_backup_and_receipt ... ok
test_hermetic_post_swap_launch_failure_rolls_code_back ... ok
Ran 2 tests
OK
```

These two pass outcomes use synthetic fixtures, NOT the installed app. The production replacement branch has **never** been exercised. The live negative gate with review run `m2-switcher-paid-credit-review-20261024-05` returned `GUARDED_RELEASE_REFUSED: REVIEW_ROOT_MISMATCH`, exit 75, with **no** installation staging/rollback/receipt directories created. Read-only `preflight` and `verify` passed the source hashes and signatures; preflight counted **46 Codex-related processes** (excluding the Switcher), so installation was blocked by session safety.

## Binary identity and scope

Candidate signed arm64 Mach-O executable:
`e0c615f92a5975e313e25e7454002000a61da107530e421f64c6751e0ea2b9cb`

Existing signed installed M2 app executable:
`edc5260ff8272d7928d2db5f2988346bf4d388643febc0a8c2ee326790716aec`

Staged app `codesign --verify --deep --strict` passed at latest read. Installer tooling is ad-hoc code-signed locally; this does not attest public updater signing, notarization, independent review, or production switching. Do not equate a package hash with proof of the 5% user path.

## Source/packet integrity

- Original implementation tree Git SHA: `d629c5be1e4da36ac0dbc451507aece99283460f`.
- Candidate patch SHA256: `8e0d04c287578ed569f810d51375c56343be602dc620126677452af48cf29f8f`.
- This packet is committed on a separate docs branch whose history contains the same immutable candidate commit. The extra docs commit is not the reviewed feature head.
- Copy of release helper SHA256: `d462da91678736e472784d1f76871360c2237fb8ccc6dbce8c5b4a2f5246604c`.
- Copy of release helper fixture tests SHA256: `ef647f7fc3e464b279d5f3435f72029658a21f7e234d98ce1f5ced62df95ad38`.
- Copy of runbook SHA256: `ab8fa5a7e432416ce45795a0c570a9cb125473c8291cc045e778e171a4bc5870`.

No production data, account ID values, account balances, cookies, refresh tokens, credentials, auth databases, or source secret files are included.
~~~

### Reviewer result contract - REVIEW_RESPONSE_TEMPLATE.md

SHA256: c5e3545b5516527e36cde43ddc6e5e0219d399364cda688b9b42865d4d02dd78

~~~markdown
# Independent reviewer response template — DO NOT PRE-FILL AS PASS

Submit the completed review from a genuinely separate author/session. The packet compiler has **not** independently reviewed it.

- Reviewer identity/session and capability:
- Independence from source author (attended OpenAI ChatGPT implementation):
- Reviewed implementation SHA: `10a1b9af293e6f4f4da20529e2dde9d1192a3525`
- Reviewed tree SHA: `d629c5be1e4da36ac0dbc451507aece99283460f`
- Reviewed release-helper SHA256 (if reviewed): `d462da91678736e472784d1f76871360c2237fb8ccc6dbce8c5b4a2f5246604c`
- Compared patch SHA256 and checked dependent source?:
- Evidence not accessible / review limitations:

## DISPOSITION: PASS | CONDITIONAL | FAIL | UNVERIFIABLE

## Blockers

Include severity, file:line, exact impact/counterexample, bounded repair, discriminating test. State NONE only after inspecting.

## Major findings

Include issue/impact/repair, or NONE.

## Nonblocking findings

Include minor quality suggestions, or NONE.

## Falsification matrix

| Behavior | Observed source evidence | Verdict/uncertainty |
|---|---|---|
| All eligible quotas strictly below 5% | | |
| Eligible/masked account completeness | | |
| Highest positive spendable credit selection | | |
| Exhaustion then next-highest credits | | |
| Active already highest; deterministic ties | | |
| Unknown/stale paid credits | | |
| Existing 1% included allowance behavior | | |
| Quota reset credit separation | | |
| Async TOCTOU and cooldown | | |
| Running-session protection | | |
| Business-member auth-token isolation | | |
| Install guard and rollback (separate) | | |

## Verification and remaining product proof

- Tests or static checks actually performed:
- Source-only review vs production proof:
- External reviewer receipt/acceptance path (if non-Fabric):
- Ready for installer? **Do not claim this merely from review PASS.** State release prerequisites, quiescence requirements and observed evidence.
- Exact recommended next action:
~~~

### Implementation exact source diff - candidate-10a1b9af.patch

SHA256: 8e0d04c287578ed569f810d51375c56343be602dc620126677452af48cf29f8f

~~~diff
diff --git a/src-tauri/src/tray.rs b/src-tauri/src/tray.rs
index 01eb5ce..cafa8c9 100644
--- a/src-tauri/src/tray.rs
+++ b/src-tauri/src/tray.rs
@@ -47,6 +47,8 @@ const QUIT_ITEM_ID: &str = "quit";
 const TRAY_WIDTH: f64 = 300.0;
 const TRAY_HEIGHT: f64 = 420.0;
 const ACCOUNT_METADATA_REFRESH_INTERVAL: Duration = Duration::from_secs(6 * 60 * 60);
+const PAID_CREDIT_FALLBACK_THRESHOLD: f64 = 5.0;
+const PAID_CREDIT_REASON: &str = "paid-credit fallback after all eligible allowance below 5%";
 
 #[derive(Clone, serde::Serialize)]
 #[serde(rename_all = "camelCase")]
@@ -800,11 +802,7 @@ fn record_auto_switch() {
     }
 }
 
-fn auto_rotation_settings_unchanged(
-    expected: &AppSettings,
-    current: &AppSettings,
-    remaining: f64,
-) -> bool {
+fn auto_rotation_settings_stable(expected: &AppSettings, current: &AppSettings) -> bool {
     !AUTO_RESET_UNCERTAIN.load(Ordering::SeqCst)
         && current.auto_switch_pause_reason.is_none()
         && current.auto_switch_enabled
@@ -816,10 +814,33 @@ fn auto_rotation_settings_unchanged(
             == expected.auto_switch_trigger_remaining_percent
         && current.auto_switch_trigger_remaining_percent.is_finite()
         && (0.5..=20.0).contains(&current.auto_switch_trigger_remaining_percent)
+}
+
+fn auto_rotation_settings_unchanged(
+    expected: &AppSettings,
+    current: &AppSettings,
+    remaining: f64,
+) -> bool {
+    auto_rotation_settings_stable(expected, current)
         && remaining.is_finite()
         && remaining <= current.auto_switch_trigger_remaining_percent
 }
 
+fn paid_credit_probe_ready(expected: &AppSettings, current: &AppSettings, remaining: f64) -> bool {
+    auto_rotation_settings_stable(expected, current)
+        && remaining.is_finite()
+        && remaining < PAID_CREDIT_FALLBACK_THRESHOLD
+}
+
+fn auto_rotation_evaluation_ready(
+    expected: &AppSettings,
+    current: &AppSettings,
+    remaining: f64,
+) -> bool {
+    auto_rotation_settings_unchanged(expected, current, remaining)
+        || paid_credit_probe_ready(expected, current, remaining)
+}
+
 fn defer_for_running_sessions(protected: bool, blocking: bool, same_account: bool) -> bool {
     protected && blocking && !same_account
 }
@@ -921,6 +942,83 @@ struct AutoRotationDecision {
     reason: &'static str,
 }
 
+// Provider spendable credit balance, NOT promotional quota-reset credits.
+fn spendable_credit_balance(usage: &UsageInfo) -> Option<f64> {
+    match (usage.has_credits, usage.unlimited_credits) {
+        (Some(false), _) => Some(0.0),
+        (Some(true), Some(true)) => Some(f64::INFINITY),
+        (Some(true), Some(false)) => {
+            let raw = usage.credits_balance.as_deref()?.trim();
+            let number = raw
+                .strip_prefix('$')
+                .or_else(|| raw.strip_prefix("USD "))
+                .unwrap_or(raw);
+            if number.is_empty()
+                || !number
+                    .chars()
+                    .all(|ch| ch.is_ascii_digit() || ch == '.' || ch == ',')
+                || number.matches('.').count() > 1
+            {
+                return None;
+            }
+            let amount = number.replace(',', "").parse::<f64>().ok()?;
+            (amount.is_finite() && amount >= 0.0).then_some(amount)
+        }
+        _ => None,
+    }
+}
+
+#[derive(Debug, PartialEq, Eq)]
+enum PaidCreditPick {
+    NotEligible,
+    KeepActive,
+    Candidate(usize),
+}
+
+/// Pure selector: a missing quota snapshot OR unknown credit amount on even
+/// one eligible account means we cannot truthfully rank all accounts.
+fn select_paid_credit_account(
+    active_usage: &UsageInfo,
+    eligible_others: &[UsageInfo],
+    expected_others: usize,
+) -> PaidCreditPick {
+    if active_usage.error.is_some()
+        || eligible_others.len() != expected_others
+        || !effective_remaining_percent(active_usage)
+            .is_some_and(|remaining| remaining < PAID_CREDIT_FALLBACK_THRESHOLD)
+    {
+        return PaidCreditPick::NotEligible;
+    }
+
+    let Some(mut best_balance) = spendable_credit_balance(active_usage) else {
+        return PaidCreditPick::NotEligible;
+    };
+    let mut best_index = None;
+    for (index, usage) in eligible_others.iter().enumerate() {
+        if usage.error.is_some()
+            || !effective_remaining_percent(usage)
+                .is_some_and(|remaining| remaining < PAID_CREDIT_FALLBACK_THRESHOLD)
+        {
+            return PaidCreditPick::NotEligible;
+        }
+        let Some(balance) = spendable_credit_balance(usage) else {
+            return PaidCreditPick::NotEligible;
+        };
+        if balance > best_balance {
+            best_balance = balance;
+            best_index = Some(index);
+        }
+    }
+
+    if best_balance <= 0.0 {
+        PaidCreditPick::NotEligible
+    } else if let Some(index) = best_index {
+        PaidCreditPick::Candidate(index)
+    } else {
+        PaidCreditPick::KeepActive
+    }
+}
+
 fn available_reset_credit(reset_credits: &AccountResetCredits) -> Option<AccountResetCredit> {
     let now = chrono::Utc::now().timestamp();
 
@@ -984,6 +1082,47 @@ async fn load_usage_candidates<R: Runtime>(
     candidates
 }
 
+fn choose_paid_credit_candidate(
+    store: &AccountsStore,
+    active_usage: &UsageInfo,
+    candidates: &[AutoRotationCandidate],
+) -> PaidCreditPick {
+    if store.active_account_id.as_deref() != Some(active_usage.account_id.as_str())
+        || store.masked_account_ids.contains(&active_usage.account_id)
+    {
+        return PaidCreditPick::NotEligible;
+    }
+    let eligible: Vec<_> = store
+        .accounts
+        .iter()
+        .filter(|account| !store.masked_account_ids.contains(&account.id))
+        .collect();
+    if !eligible
+        .iter()
+        .any(|account| account.id == active_usage.account_id)
+    {
+        return PaidCreditPick::NotEligible;
+    }
+    let other_ids: std::collections::HashSet<_> = eligible
+        .iter()
+        .filter(|account| account.id != active_usage.account_id)
+        .map(|account| account.id.as_str())
+        .collect();
+    let candidate_ids: std::collections::HashSet<_> = candidates
+        .iter()
+        .filter(|candidate| candidate.account.id == candidate.usage.account_id)
+        .map(|candidate| candidate.account.id.as_str())
+        .collect();
+    if other_ids != candidate_ids || candidates.len() != other_ids.len() {
+        return PaidCreditPick::NotEligible;
+    }
+    let snapshots: Vec<_> = candidates
+        .iter()
+        .map(|candidate| candidate.usage.clone())
+        .collect();
+    select_paid_credit_account(active_usage, &snapshots, other_ids.len())
+}
+
 fn best_remaining_candidate(
     candidates: &[AutoRotationCandidate],
     min_remaining_exclusive: f64,
@@ -1379,7 +1518,7 @@ fn maybe_auto_switch_account<R: Runtime>(
     let Some(active_remaining) = effective_remaining_percent(active_usage) else {
         return;
     };
-    if !auto_rotation_settings_unchanged(&settings, &settings, active_remaining) {
+    if !auto_rotation_evaluation_ready(&settings, &settings, active_remaining) {
         return;
     }
 
@@ -1404,38 +1543,67 @@ fn maybe_auto_switch_account<R: Runtime>(
         if current_store.active_account_id.as_deref() != Some(active_id.as_str())
             || !auto_switch_cooldown_ready(cooldown)
             || !load_app_settings()
-                .map(|latest| {
-                    auto_rotation_settings_unchanged(&settings, &latest, active_remaining)
-                })
+                .map(|latest| auto_rotation_evaluation_ready(&settings, &latest, active_remaining))
                 .unwrap_or(false)
         {
             return;
         }
 
-        let decision = match settings.auto_rotation_mode {
-            AutoRotationMode::PreserveResets => {
-                preserve_resets_decision(
-                    &app,
-                    &current_store,
-                    &active_usage,
-                    active_remaining,
-                    settings.auto_switch_trigger_remaining_percent,
-                    settings.auto_switch_candidate_min_remaining_percent,
-                    settings.auto_switch_fallback_min_remaining_percent,
-                )
-                .await
+        // Before either reset strategy, consider real spendable balances. The
+        // credit tier is triggered at 5% independently of the saved 1% normal
+        // allowance trigger; quota-reset promotions are a different resource.
+        let mut credit_decision = None;
+        if paid_credit_probe_ready(&settings, &settings, active_remaining) {
+            let credit_candidates = load_usage_candidates(&app, &current_store, &active_id).await;
+            match choose_paid_credit_candidate(&current_store, &active_usage, &credit_candidates) {
+                PaidCreditPick::KeepActive => {
+                    record_auto_switch();
+                    println!(
+                        "[AutoSwitch] Current account already has the largest paid credit balance"
+                    );
+                    return;
+                }
+                PaidCreditPick::Candidate(index) => {
+                    credit_decision = Some(AutoRotationDecision {
+                        candidate: credit_candidates[index].clone(),
+                        reset_credit: None,
+                        reason: PAID_CREDIT_REASON,
+                    });
+                }
+                PaidCreditPick::NotEligible => {}
             }
-            AutoRotationMode::ConcentrateBurn => {
-                concentrate_burn_decision(
-                    &app,
-                    &current_store,
-                    &active_usage,
-                    active_remaining,
-                    settings.auto_switch_trigger_remaining_percent,
-                )
-                .await
+        }
+
+        let decision = if credit_decision.is_some() {
+            credit_decision
+        } else if auto_rotation_settings_unchanged(&settings, &settings, active_remaining) {
+            match settings.auto_rotation_mode {
+                AutoRotationMode::PreserveResets => {
+                    preserve_resets_decision(
+                        &app,
+                        &current_store,
+                        &active_usage,
+                        active_remaining,
+                        settings.auto_switch_trigger_remaining_percent,
+                        settings.auto_switch_candidate_min_remaining_percent,
+                        settings.auto_switch_fallback_min_remaining_percent,
+                    )
+                    .await
+                }
+                AutoRotationMode::ConcentrateBurn => {
+                    concentrate_burn_decision(
+                        &app,
+                        &current_store,
+                        &active_usage,
+                        active_remaining,
+                        settings.auto_switch_trigger_remaining_percent,
+                    )
+                    .await
+                }
+                AutoRotationMode::Manual => None,
             }
-            AutoRotationMode::Manual => None,
+        } else {
+            None
         };
 
         match decision {
@@ -1452,11 +1620,20 @@ fn maybe_auto_switch_account<R: Runtime>(
                 let Some(fresh_remaining) = effective_remaining_percent(&fresh_usage) else {
                     return;
                 };
+                let paid_credit_mode = decision.reason == PAID_CREDIT_REASON;
                 if fresh_usage.error.is_some()
                     || fresh_usage.account_id != active_id
                     || !load_app_settings()
                         .map(|latest| {
-                            auto_rotation_settings_unchanged(&settings, &latest, fresh_remaining)
+                            if paid_credit_mode {
+                                paid_credit_probe_ready(&settings, &latest, fresh_remaining)
+                            } else {
+                                auto_rotation_settings_unchanged(
+                                    &settings,
+                                    &latest,
+                                    fresh_remaining,
+                                )
+                            }
                         })
                         .unwrap_or(false)
                     || !load_accounts()
@@ -1466,6 +1643,47 @@ fn maybe_auto_switch_account<R: Runtime>(
                     return;
                 }
 
+                if paid_credit_mode {
+                    // Refresh the complete eligible pool, not just the chosen
+                    // account: a spent balance or another account's recovery
+                    // invalidates the old highest-credit choice.
+                    let Ok(latest_store) = load_accounts() else {
+                        return;
+                    };
+                    let fresh_candidates =
+                        load_usage_candidates(&app, &latest_store, &active_id).await;
+                    match choose_paid_credit_candidate(
+                        &latest_store,
+                        &fresh_usage,
+                        &fresh_candidates,
+                    ) {
+                        PaidCreditPick::Candidate(index)
+                            if fresh_candidates[index].account.id
+                                == decision.candidate.account.id =>
+                        {
+                            // No-op: the intended winner still ranks first.
+                        }
+                        _ => {
+                            eprintln!(
+                                "[AutoSwitch] Paid-credit destination changed; not switching"
+                            );
+                            record_auto_switch();
+                            return;
+                        }
+                    }
+                    if !load_app_settings()
+                        .map(|latest| paid_credit_probe_ready(&settings, &latest, fresh_remaining))
+                        .unwrap_or(false)
+                        || !load_accounts()
+                            .map(|store| {
+                                store.active_account_id.as_deref() == Some(active_id.as_str())
+                            })
+                            .unwrap_or(false)
+                    {
+                        return;
+                    }
+                }
+
                 if settings.auto_switch_protect_running_sessions
                     && decision.candidate.account.id != active_id
                 {
@@ -1533,6 +1751,122 @@ fn poll_account_metadata<R: Runtime>(app: AppHandle<R>) {
 mod tests {
     use super::*;
 
+    fn credit_usage(id: &str, remaining: f64, balance: &str) -> UsageInfo {
+        let mut usage = UsageInfo::error(id.into(), "synthetic".into());
+        usage.error = None;
+        usage.primary_used_percent = Some(100.0 - remaining);
+        usage.secondary_used_percent = Some(100.0 - remaining);
+        usage.has_credits = Some(true);
+        usage.unlimited_credits = Some(false);
+        usage.credits_balance = Some(balance.into());
+        usage
+    }
+
+    #[test]
+    fn credit_fallback_selects_highest_balance_after_all_below_five() {
+        let active = credit_usage("active", 4.9, "$20.00");
+        let others = [
+            credit_usage("b", 4.0, "$71.25"),
+            credit_usage("c", 0.1, "$15.00"),
+        ];
+        assert_eq!(
+            select_paid_credit_account(&active, &others, 2),
+            PaidCreditPick::Candidate(0)
+        );
+        let exhausted = credit_usage("active", 0.0, "$0.00");
+        assert_eq!(
+            select_paid_credit_account(&exhausted, &others, 2),
+            PaidCreditPick::Candidate(0)
+        );
+    }
+
+    #[test]
+    fn credit_fallback_retains_best_active_and_prefers_unlimited() {
+        let active = credit_usage("active", 0.0, "$101.00");
+        let others = [credit_usage("b", 3.0, "$100.00")];
+        assert_eq!(
+            select_paid_credit_account(&active, &others, 1),
+            PaidCreditPick::KeepActive
+        );
+        let mut unlimited = others[0].clone();
+        unlimited.unlimited_credits = Some(true);
+        unlimited.credits_balance = None;
+        assert_eq!(
+            select_paid_credit_account(&active, &[unlimited], 1),
+            PaidCreditPick::Candidate(0)
+        );
+    }
+
+    #[test]
+    fn credit_fallback_refuses_incomplete_quota_or_credit_census() {
+        let active = credit_usage("active", 4.0, "$10.00");
+        let high_allowance = credit_usage("b", 5.0, "$100.00");
+        assert_eq!(
+            select_paid_credit_account(&active, &[high_allowance], 1),
+            PaidCreditPick::NotEligible
+        );
+        assert_eq!(
+            select_paid_credit_account(&active, &[], 1),
+            PaidCreditPick::NotEligible
+        );
+        let mut missing_quota = credit_usage("b", 0.0, "$100.00");
+        missing_quota.primary_used_percent = None;
+        missing_quota.secondary_used_percent = None;
+        assert_eq!(
+            select_paid_credit_account(&active, &[missing_quota], 1),
+            PaidCreditPick::NotEligible
+        );
+        let mut missing_balance = credit_usage("b", 0.0, "$100.00");
+        missing_balance.credits_balance = None;
+        assert_eq!(
+            select_paid_credit_account(&active, &[missing_balance], 1),
+            PaidCreditPick::NotEligible
+        );
+        let mut missing_flag = credit_usage("b", 0.0, "$100.00");
+        missing_flag.has_credits = None;
+        assert_eq!(
+            select_paid_credit_account(&active, &[missing_flag], 1),
+            PaidCreditPick::NotEligible
+        );
+    }
+
+    #[test]
+    fn credit_fallback_disallows_invalid_or_exhausted_balances() {
+        let active = credit_usage("active", 0.0, "$0.00");
+        let zero = credit_usage("b", 0.0, "$0.00");
+        assert_eq!(
+            select_paid_credit_account(&active, &[zero], 1),
+            PaidCreditPick::NotEligible
+        );
+        for value in ["-1", "NaN", "$", "Infinity", "25 CAD"] {
+            let bad = credit_usage("b", 0.0, value);
+            assert_eq!(spendable_credit_balance(&bad), None);
+        }
+        assert_eq!(
+            spendable_credit_balance(&credit_usage("a", 0.0, "$1,025.30")),
+            Some(1025.3)
+        );
+    }
+
+    #[test]
+    fn credit_probe_is_independent_of_one_percent_reset_trigger() {
+        let settings = AppSettings::default();
+        assert!(paid_credit_probe_ready(&settings, &settings, 4.9));
+        assert!(auto_rotation_evaluation_ready(&settings, &settings, 4.9));
+        assert!(!auto_rotation_settings_unchanged(&settings, &settings, 4.9));
+        assert!(!paid_credit_probe_ready(&settings, &settings, 5.0));
+        assert!(!paid_credit_probe_ready(&settings, &settings, f64::NAN));
+        let mut disabled = settings.clone();
+        disabled.auto_switch_enabled = false;
+        assert!(!paid_credit_probe_ready(&settings, &disabled, 1.0));
+        let mut paused = settings.clone();
+        paused.auto_switch_pause_reason = Some("Uncertain reset".into());
+        assert!(!paid_credit_probe_ready(&settings, &paused, 1.0));
+        let mut manual = settings.clone();
+        manual.auto_rotation_mode = AutoRotationMode::Manual;
+        assert!(!paid_credit_probe_ready(&settings, &manual, 1.0));
+    }
+
     #[test]
     fn automatic_rotation_requires_fresh_enabled_policy_and_threshold() {
         let expected = AppSettings::default();
~~~

### Guarded release helper source - guarded_release.py

SHA256: d462da91678736e472784d1f76871360c2237fb8ccc6dbce8c5b4a2f5246604c

~~~python
#!/usr/bin/env python3
"""M2 Codex Switcher credit fallback release. No effects except in --install."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

HOME = Path.home()
SOURCE = HOME / "agent-workspaces/codex-switcher-m2-paid-credit-fallback-20261023"
LIVE = Path("/Applications/Codex Switcher.app")
CANDIDATE = SOURCE / "src-tauri/target/release/bundle/macos/Codex Switcher.app"
RELEASE = HOME / "agent-workspaces/codex-switcher-paid-credit-release-20261024"
NATIVE_FABRIC = HOME / ".claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/native-code-releases/6957399841a2913d5a32deedd633e4c4b5124c3199d0e804fc8a6abe69e8ef51/ext/fabric_task.py"
HEAD = "10a1b9af293e6f4f4da20529e2dde9d1192a3525"
TARGET_SHA = "e0c615f92a5975e313e25e7454002000a61da107530e421f64c6751e0ea2b9cb"
ORIGINAL_SHA = "edc5260ff8272d7928d2db5f2988346bf4d388643febc0a8c2ee326790716aec"
ROOT = "m2-switcher-credit-fallback-20261023"
EXEC = "Contents/MacOS/codex-switcher"
STAGING = Path("/Applications/.CodexSwitcher-credit-stage-10a1b9af.app")
ROLLBACK = Path("/Applications/.CodexSwitcher-credit-rollback-10a1b9af.app")
FAILED = Path("/Applications/.CodexSwitcher-credit-failed-10a1b9af.app")
RECEIPT = RELEASE / "installation-receipt.json"

def command(*args, timeout=45):
    return subprocess.check_output(list(map(str, args)), stderr=subprocess.STDOUT, timeout=timeout)

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for b in iter(lambda: stream.read(1048576), b""):
            h.update(b)
    return h.hexdigest()

def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)

def signature(app):
    command("/usr/bin/codesign", "--verify", "--deep", "--strict", app)

def git_identity():
    actual = command("/usr/bin/git", "-C", SOURCE, "rev-parse", "HEAD").decode().strip()
    require(actual == HEAD, "SOURCE_HEAD_CHANGED: " + actual)
    dirty = command("/usr/bin/git", "-C", SOURCE, "status", "--porcelain")
    require(not dirty.strip(), "SOURCE_WORKTREE_DIRTY")

def codex_processes():
    raw = command("/bin/ps", "-axo", "pid=,comm=").decode()
    result = []
    for line in raw.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        name = Path(parts[1]).name.lower()
        if (name == "codex" or name.startswith("codex ") or
                name.startswith("codex-") or name.startswith("codex_")):
            if name != "codex-switcher":
                result.append((int(parts[0]), name))
    return result

def switcher_pids():
    exact = str(LIVE / EXEC)
    raw = command("/bin/ps", "-axo", "pid=,command=").decode()
    return [int(parts[0]) for line in raw.splitlines()
            if len(parts := line.strip().split(None, 1)) == 2
            and parts[0].isdigit()
            and (parts[1] == exact or parts[1].startswith(exact + " "))]

def auth_fingerprints():
    files = (HOME / ".codex-switcher/accounts.json",
             HOME / ".codex-switcher/settings.json",
             HOME / ".codex/auth.json")
    return {str(path): digest(path) if path.is_file() else None for path in files}

def guarded_settings():
    path = HOME / ".codex-switcher/settings.json"
    require(path.is_file() and path.stat().st_size < 1000000,
            "SETTINGS_UNAVAILABLE_OR_OVERSIZED")
    settings = json.loads(path.read_text())
    require(settings.get("auto_switch_protect_running_sessions") is True,
            "SESSION_PROTECTION_DISABLED_DO_NOT_INSTALL")
    require(settings.get("auto_switch_pause_reason") is None,
            "UNRESOLVED_AUTO_ROTATION_PAUSE")
    require(settings.get("auto_switch_enabled") is True,
            "AUTO_SWITCH_DISABLED_CHECK_OPERATOR_INTENT")
    require(settings.get("auto_switch_trigger_remaining_percent") == 1.0,
            "INCLUDED_USAGE_TRIGGER_CHANGED_REVIEW_REQUIRED")
    return settings

def baseline():
    git_identity()
    require(CANDIDATE.is_dir() and LIVE.is_dir(), "MISSING_APP_BUNDLE")
    require(digest(CANDIDATE / EXEC) == TARGET_SHA, "STAGED_BINARY_HASH_MISMATCH")
    require(digest(LIVE / EXEC) == ORIGINAL_SHA, "INSTALLED_PREIMAGE_MOVED")
    signature(CANDIDATE)
    signature(LIVE)

def accepted_review(run_id, response_sha):
    require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", run_id)), "INVALID_REVIEW_RUN")
    require(bool(re.fullmatch(r"[0-9a-f]{64}", response_sha)), "INVALID_REVIEW_SHA")
    require(NATIVE_FABRIC.is_file(), "NATIVE_FABRIC_MISSING")
    status = json.loads(command(sys.executable, NATIVE_FABRIC, "status", run_id).decode())
    require(status.get("run_id") == run_id and status.get("root_id") == ROOT, "REVIEW_ROOT_MISMATCH")
    require(status.get("state") == "TERMINAL" and status.get("rc") == 0
            and status.get("signal") == "ok" and status.get("result_available") is True,
            "REVIEW_NOT_SUCCESSFULLY_TERMINAL")
    require(status.get("accepted") is True and status.get("accepted_by") == "reviewer"
            and status.get("acceptance_state") == "ACCEPTED",
            "REVIEW_NOT_INDEPENDENTLY_ACCEPTED")
    response = command(sys.executable, NATIVE_FABRIC, "result", run_id)
    require(hashlib.sha256(response).hexdigest() == response_sha, "REVIEW_RESULT_HASH_MISMATCH")
    review_text = response.decode("utf-8", errors="strict")
    require(HEAD in review_text, "REVIEW_NOT_BOUND_TO_EXACT_SOURCE_HEAD")
    require(bool(re.search(r"(?mi)^\s*(?:DISPOSITION|VERDICT)\s*:\s*PASS\b", review_text)),
            "REVIEW_NO_EXPLICIT_PASS")
    return status

def preflight():
    baseline()
    guarded_settings()
    blockers = codex_processes()
    pids = switcher_pids()
    require(pids, "INSTALLED_SWITCHER_NOT_RUNNING")
    print(json.dumps({
        "state": "PREPARED_ONLY_NO_INSTALL",
        "head": HEAD, "staged_sha256": TARGET_SHA,
        "installed_sha256": ORIGINAL_SHA, "signatures": "PASS",
        "running_switcher_count": len(pids),
        "codex_session_guard_count": len(blockers),
        "install_session_gate": "BLOCKED" if blockers else "QUIESCENT",
        "independent_review": "MUST_BE_ACCEPTED",
        "auth_files": "NEVER_COPIED_OR_RESTORED",
    }, indent=2, sort_keys=True))

def wait_for_switcher_stop(pids, timeout=12):
    for pid in pids:
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not switcher_pids():
            return
        time.sleep(0.25)
    raise RuntimeError("SWITCHER_DID_NOT_STOP_GRACEFULLY_NO_FORCE_KILL")

def start_and_verify(expected, timeout=15):
    command("/usr/bin/open", "-a", LIVE)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if switcher_pids() and digest(LIVE / EXEC) == expected:
            signature(LIVE)
            return switcher_pids()
        time.sleep(0.4)
    raise RuntimeError("NEW_APP_DID_NOT_LAUNCH_VERIFIABLY")

def install(review_run, response_sha):
    # Review and immutable-source checks occur BEFORE copying or stopping anything.
    accepted_review(review_run, response_sha)
    baseline()
    guarded_settings()
    require(not RECEIPT.exists(), "EXISTING_INSTALL_RECEIPT_RECONCILE_FIRST")
    for path in (STAGING, ROLLBACK, FAILED):
        require(not path.exists(), "RESIDUAL_INSTALL_PATH_RECONCILE_FIRST: " + str(path))
    require(shutil.disk_usage("/Applications").free > 1024 ** 3, "LOW_INSTALL_DISK")
    require(not codex_processes(), "LIVE_CODEX_SESSIONS_PRESENT_NO_INSTALL")
    require(os.access("/Applications", os.W_OK), "APPLICATIONS_NOT_WRITABLE")
    switcher = switcher_pids()
    require(len(switcher) == 1, "SWITCHER_PROCESS_IDENTITY_UNCERTAIN")
    before_auth = auth_fingerprints()

    # Back up original app, not account/auth stores. Stage complete signed app first.
    backup = RELEASE / ("original-" + ORIGINAL_SHA[:12] + ".app")
    require(not backup.exists(), "EXISTING_BACKUP_RECONCILE_FIRST")
    command("/usr/bin/ditto", LIVE, backup, timeout=180)
    require(digest(backup / EXEC) == ORIGINAL_SHA, "BACKUP_BINARY_MISMATCH")
    signature(backup)
    command("/usr/bin/ditto", CANDIDATE, STAGING, timeout=180)
    require(digest(STAGING / EXEC) == TARGET_SHA, "STAGED_INSTALL_COPY_HASH_MISMATCH")
    signature(STAGING)
    baseline()
    guarded_settings()
    require(not codex_processes(), "LIVE_CODEX_SESSIONS_APPEARED_NO_INSTALL")

    # No SIGKILL and no process/session redirection. If stop fails, leave original installed.
    wait_for_switcher_stop(switcher)
    try:
        os.rename(LIVE, ROLLBACK)
    except Exception:
        # Nothing has been replaced; restart the known original.
        start_and_verify(ORIGINAL_SHA)
        raise RuntimeError("STAGING_RENAME_FAILED_ORIGINAL_RESTARTED")
    try:
        os.rename(STAGING, LIVE)
    except Exception:
        try:
            os.rename(ROLLBACK, LIVE)
            start_and_verify(ORIGINAL_SHA)
        except Exception as restore_error:
            raise RuntimeError("SWAP_RECOVERY_EFFECT_UNCERTAIN") from restore_error
        raise RuntimeError("SWAP_FAILED_ORIGINAL_RESTORED")

    try:
        require(digest(LIVE / EXEC) == TARGET_SHA, "INSTALLED_NEW_BINARY_MISMATCH")
        signature(LIVE)
        running = start_and_verify(TARGET_SHA)
    except Exception:
        # Roll back code only. Do not restore old OAuth/token files.
        try:
            os.rename(LIVE, FAILED)
            os.rename(ROLLBACK, LIVE)
            start_and_verify(ORIGINAL_SHA)
        except Exception as rollback_error:
            raise RuntimeError("ROLLBACK_EFFECT_UNCERTAIN_RECONCILE_MANUALLY") from rollback_error
        raise RuntimeError("APP_LAUNCH_FAILED_BINARY_ROLLED_BACK")

    changed = [name for name, old in before_auth.items()
               if auth_fingerprints().get(name) != old]
    record = {
        "schema": "mmx.codex_switcher_local_release_receipt.v1",
        "installed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "review_run": review_run, "review_response_sha256": response_sha,
        "candidate_head": HEAD, "installed_sha256": TARGET_SHA,
        "original_sha256": ORIGINAL_SHA, "original_bundle_backup": str(backup),
        "original_bundle_rollback": str(ROLLBACK),
        "verified_running_pid_count": len(running),
        "auth_paths_changed_count": len(changed),
        "auth_paths_restored": False,
        "real_credit_exhaustion_proven": False
    }
    data = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
    try:
        fd = os.open(RECEIPT, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    except OSError as receipt_error:
        raise RuntimeError("INSTALLED_BUT_RECEIPT_WRITE_FAILED_EFFECT_RECONCILE") from receipt_error
    print(json.dumps(record, indent=2, sort_keys=True))
    if changed:
        raise RuntimeError("INSTALLED_BUT_AUTH_STORE_CHANGED_REVIEW_BEFORE_ACCEPTANCE")

def verify():
    git_identity()
    require(LIVE.is_dir(), "INSTALLED_APP_MISSING")
    actual = digest(LIVE / EXEC)
    signature(LIVE)
    print(json.dumps({"installed_sha256": actual,
                      "is_candidate": actual == TARGET_SHA,
                      "is_original": actual == ORIGINAL_SHA,
                      "switcher_pids": switcher_pids(),
                      "active_codex_process_count": len(codex_processes()),
                      "receipt_exists": RECEIPT.exists(),
                      "credit_fallback_real_transition_proven": False},
                     indent=2, sort_keys=True))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["preflight", "install", "verify"])
    parser.add_argument("--review-run")
    parser.add_argument("--review-response-sha256")
    args = parser.parse_args()
    if args.action == "preflight":
        preflight()
    elif args.action == "verify":
        verify()
    else:
        require(bool(args.review_run and args.review_response_sha256),
                "ACCEPTED_INDEPENDENT_REVIEW_REQUIRED")
        install(args.review_run, args.review_response_sha256)

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        detail = str(error)
        effect_unknown = ("EFFECT_UNCERTAIN" in detail or
                          detail.startswith("INSTALLED_BUT"))
        prefix = "RELEASE_EFFECT_RECONCILE: " if effect_unknown else "GUARDED_RELEASE_REFUSED: "
        print(prefix + detail, file=sys.stderr)
        sys.exit(78 if effect_unknown else 75)
~~~

### Release fixture tests - test_guarded_release.py

SHA256: ef647f7fc3e464b279d5f3435f72029658a21f7e234d98ce1f5ced62df95ad38

~~~python
#!/usr/bin/env python3
"""Pure temporary-fixture tests; never touches the M2 installed application."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

HELPER = Path(__file__).with_name("guarded_release.py")

class GuardedReleaseFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mmx-credit-release-fixture-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        spec = importlib.util.spec_from_file_location("guarded_release_fixture", HELPER)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        a = self.mod
        a.RELEASE = root / "release"
        a.RELEASE.mkdir()
        a.LIVE = root / "Applications/Codex Switcher.app"
        a.CANDIDATE = root / "candidate/Codex Switcher.app"
        a.STAGING = root / "Applications/.credit-stage.app"
        a.ROLLBACK = root / "Applications/.credit-rollback.app"
        a.FAILED = root / "Applications/.credit-failed.app"
        a.RECEIPT = a.RELEASE / "installation-receipt.json"
        a.LIVE.joinpath("Contents/MacOS").mkdir(parents=True)
        a.CANDIDATE.joinpath("Contents/MacOS").mkdir(parents=True)
        (a.LIVE / a.EXEC).write_bytes(b"original app code")
        (a.CANDIDATE / a.EXEC).write_bytes(b"candidate app code")
        a.ORIGINAL_SHA = a.digest(a.LIVE / a.EXEC)
        a.TARGET_SHA = a.digest(a.CANDIDATE / a.EXEC)
        a.accepted_review = lambda run, sha: {"accepted": True}  # fixture only
        a.guarded_settings = lambda: {}
        a.git_identity = lambda: None
        a.signature = lambda _: None
        a.codex_processes = lambda: []
        a.switcher_pids = lambda: [12345]  # synthetic PID; never signaled
        a.wait_for_switcher_stop = lambda pids: None
        a.auth_fingerprints = lambda: {"fixture_auth": "unchanged"}
        self.access_patch = mock.patch.object(a.os, "access", return_value=True)
        self.access_patch.start()
        self.addCleanup(self.access_patch.stop)
        def fake_command(*args, **kwargs):
            if str(args[0]) != "/usr/bin/ditto":
                raise AssertionError("unexpected external command in fixture")
            shutil.copytree(args[1], args[2])
            return b""
        a.command = fake_command

    def test_hermetic_install_swap_backup_and_receipt(self):
        a = self.mod
        a.start_and_verify = lambda expected: (
            [67890] if a.digest(a.LIVE / a.EXEC) == expected
            else (_ for _ in ()).throw(RuntimeError("wrong app hash")))
        a.install("review-fixture", "f" * 64)
        self.assertEqual(a.digest(a.LIVE / a.EXEC), a.TARGET_SHA)
        self.assertEqual(a.digest(a.ROLLBACK / a.EXEC), a.ORIGINAL_SHA)
        backup = a.RELEASE / ("original-" + a.ORIGINAL_SHA[:12] + ".app")
        self.assertEqual(a.digest(backup / a.EXEC), a.ORIGINAL_SHA)
        receipt = json.loads(a.RECEIPT.read_text())
        self.assertEqual(receipt["installed_sha256"], a.TARGET_SHA)
        self.assertEqual(receipt["auth_paths_changed_count"], 0)

    def test_hermetic_post_swap_launch_failure_rolls_code_back(self):
        a = self.mod
        def launch(expected):
            if expected == a.TARGET_SHA:
                raise RuntimeError("synthetic launch failure")
            self.assertEqual(a.digest(a.LIVE / a.EXEC), a.ORIGINAL_SHA)
            return [67890]
        a.start_and_verify = launch
        with self.assertRaisesRegex(RuntimeError, "APP_LAUNCH_FAILED_BINARY_ROLLED_BACK"):
            a.install("review-fixture", "f" * 64)
        self.assertEqual(a.digest(a.LIVE / a.EXEC), a.ORIGINAL_SHA)
        self.assertEqual(a.digest(a.FAILED / a.EXEC), a.TARGET_SHA)
        self.assertFalse(a.RECEIPT.exists())

if __name__ == "__main__":
    unittest.main(verbosity=2)
~~~

### Deployment and rollback runbook - RELEASE_RUNBOOK.md

SHA256: ab8fa5a7e432416ce45795a0c570a9cb125473c8291cc045e778e171a4bc5870

~~~markdown
# M2 Codex Switcher — paid-credit fallback, guarded local release

Status as of 2026-10-24: **BUILT_NOT_PROVEN / RELEASE HOLD**. This is a manual release aid, not a scheduler, daemon, privilege waiver, or evidence of an approved review. Source and production effects are separate.

## Immutable identity and existing proof

- Source worktree: `/Users/chriswong/agent-workspaces/codex-switcher-m2-paid-credit-fallback-20261023`
- Source HEAD: `10a1b9af293e6f4f4da20529e2dde9d1192a3525`
- Candidate app: `src-tauri/target/release/bundle/macos/Codex Switcher.app` under the source worktree
- Candidate executable SHA256: `e0c615f92a5975e313e25e7454002000a61da107530e421f64c6751e0ea2b9cb`; macOS ad-hoc signature verifies. Local only: updater archive signing requires a private key not provided.
- Currently installed executable SHA256: `edc5260ff8272d7928d2db5f2988346bf4d388643febc0a8c2ee326790716aec`
- Tests from unchanged exact head: Rust 86 pass, 1 ignored, and frontend tests 7+3+3 pass. No real 5%-quota credit transition has been verified.
- Independent source material on M1: `/Users/chriswong/lanes/codex-switcher-review-20261024-03`, patch SHA256 `8e0d04c287578ed569f810d51375c56343be602dc620126677452af48cf29f8f`.
- GLM review run `m2-switcher-paid-credit-review-20261024-05` was explicitly refused before launch: `NONE reason=pool glm has no eligible mode on requested host`; native Fabric status `REQUEST_REFUSED_BEFORE_LAUNCH`. All earlier Qwen attempts were unaccepted. Do NOT replay any terminal operation or force a host past admission.

## Release gates — all required before application replacement

1. A new eligible, independent reviewer actually executes through an admitted Fabric provider/host, reviews this exact source HEAD and dependency closure, and returns explicit **DISPOSITION: PASS**. The current operator adjudicates any findings. Modified source requires new exact-head tests/build/signature and a fresh independent review.
2. Native Fabric terminal status for that reviewer has `rc=0`, `signal=ok`, `result_available=true`, `accepted=true`, `accepted_by=reviewer`, `acceptance_state=ACCEPTED`, and the correct parent root. Record the exact *complete* result SHA256. Merely delivering the request or acquiring a provider lease is insufficient.
3. Source and staged bundle are byte-identical to the hashes above, clean Git HEAD, valid macOS signatures, and installed baseline executable still matches the old hash. Otherwise stop and reconcile.
4. Codex session protection remains enabled. **Zero local Codex-related processes other than the Switcher itself** is required for this conservative installer. The prior preflight saw 46 such processes. Do not kill worker or interactive Codex processes to meet the gate. The installer only SIGTERMs the known Switcher, never SIGKILLs and never operates on other Codex processes.
5. Existing auth/profile files remain owned by the application: `~/.codex-switcher/accounts.json`, `~/.codex-switcher/settings.json`, `~/.codex/auth.json`. Do not copy, restore or replay an old OAuth refresh token. An updated or uncertain reset pause must be inspected rather than cleared to facilitate installation.

## Prepared commands

From M2, first run read-only checks:

```sh
python3 ~/agent-workspaces/codex-switcher-paid-credit-release-20261024/guarded_release.py preflight
python3 ~/agent-workspaces/codex-switcher-paid-credit-release-20261024/guarded_release.py verify
```

After an actual Fabric reviewer PASS and reviewer acceptance receipt **and only when the session gate is QUIESCENT**, set `RUN_ID` to the actual *new successful* review and `RESPONSE_SHA256` to the verified full result digest, then run:

```sh
RUN_ID='<accepted-independent-Fabric-review-run-id>'
RESPONSE_SHA256='<verified-full-review-result-sha256>'
python3 ~/agent-workspaces/codex-switcher-paid-credit-release-20261024/guarded_release.py install --review-run "$RUN_ID" --review-response-sha256 "$RESPONSE_SHA256"
python3 ~/agent-workspaces/codex-switcher-paid-credit-release-20261024/guarded_release.py verify
```

The script refuses installation unless it can read an independently **reviewer-accepted** status for the exact root and exact commit, validates result digest and explicit PASS, rechecks original/staged executable hashes and signatures, and requires no other Codex processes. It backs up the original app bundle (not auth) under this directory, makes an additional rollback app inside `/Applications`, stages and verifies a complete signed app bundle, terminates only the old Switcher after quiescence, atomically renames the staged app into place, launches the new app, checks its running process and executable hash, and writes an exclusive permission-0600 installation receipt. Automatic failure rollback restores **code only**, never an OAuth/account/settings snapshot. Any uncertain swap or missing receipt requires direct readback before retry, not blind replay. This helper's real install branch has **not** been exercised or independently audited; review the specific release script before invoking it for real.

## After installation: live product-path verification

- Confirm `guarded_release.py verify` reports the candidate SHA installed, a fresh running Switcher PID, and that the installation receipt exists. Verify app codesign.
- Confirm the UI launches and the account list still contains its legitimate Personal Pro and Business records, without displaying secrets. Confirm auto-switch enabled, normal included-quota trigger remains at 1%, running-session protection enabled, and no unintended pause/reset-credit consumption.
- Check actual usage and paid-credit balances via the Switcher's normal read-only UI/provider observation path. Distinguish paid balance from promotional reset credits. Do not synthesize quota values in production or issue a reset POST merely to make proof pass.
- At a naturally observed state where **all eligible unmasked accounts** have less than 5% effective allowance remaining, confirm that the current account with the largest valid spendable paid balance is retained; if another has more, automatic switching targets it only when no protected Codex sessions are active. When the active paid balance naturally empties, the next highest positive balance should be selected. Missing/incomplete balances must prevent unsupported ranking. Capture observation timestamps, eligible-account counts, the selected account ID hash (not credentials), and the relevant Switcher process/UI/log evidence.
- Separately validate that accounts at or above the 5% boundary follow the original allowance logic, and that business-member token isolation remains intact; no duplicate refresh/identity writer. Do not claim full production proof until meaningful real-path behavior is observed.

## Rollback and recovery boundaries

- Old app bundle is backed up under the release directory as `original-edc5260ff827.app` and moved during swap to `/Applications/.CodexSwitcher-credit-rollback-10a1b9af.app`. The installer retains both.
- If initial new app launch fails, the installer attempts rollback automatically, with exact SHA and fresh process verification. If it reports `RELEASE_EFFECT_RECONCILE`, inspect live bundle hash, process identity, rollback directories, and receipt on the original M2 path before attempting anything else.
- A later manual rollback must first confirm zero active Codex sessions and reconcile the installed binary, then restore the previous app bundle and relaunch it. Do not restore old copies of account credentials/settings, and do not force-quiesce sessions.
- The app's upstream updater may replace the custom build. Future upstream updates require compatibility review.

## Durable continuation

Source is ready; currently missing gate is **admitted non-Qwen reviewer host/provider and accepted independent exact-head review**. The previously pinned GLM task was refused before launch. Do not use the terminal run IDs as approval. After a genuine provider/host eligibility change, commission a fresh lawful reviewer and carry accepted findings through requalification and guarded release. See the existing cumulative checkpoint at `~/agent-workspaces/CODEX_SWITCHER_PAID_CREDIT_FALLBACK_CHECKPOINT_20261024.md`.
~~~

### Machine-readable manifest - MANIFEST.json

SHA256: addbb5b47643adcdeef51970e8abf6a41f84e114969190f16f21cd062d34f8d0

~~~json
{
  "accepted_independent_review": false,
  "base_sha": "a744e4f8128db1074e91b4f18e16b445fab40af6",
  "candidate_tree_sha": "d629c5be1e4da36ac0dbc451507aece99283460f",
  "files_sha256": {
    "EVIDENCE.md": "0b3a791e7fcdaf6ce968dd10bb9d46eb65b34cd51114af510190f094f4e088bf",
    "README.md": "50ea9398d88963da65d9a2c005df006d06dadbe3e34a6db5c94a3605f702a168",
    "RELEASE_RUNBOOK.md": "ab8fa5a7e432416ce45795a0c570a9cb125473c8291cc045e778e171a4bc5870",
    "REVIEW_RESPONSE_TEMPLATE.md": "c5e3545b5516527e36cde43ddc6e5e0219d399364cda688b9b42865d4d02dd78",
    "candidate-10a1b9af.patch": "8e0d04c287578ed569f810d51375c56343be602dc620126677452af48cf29f8f",
    "guarded_release.py": "d462da91678736e472784d1f76871360c2237fb8ccc6dbce8c5b4a2f5246604c",
    "test_guarded_release.py": "ef647f7fc3e464b279d5f3435f72029658a21f7e234d98ce1f5ced62df95ad38"
  },
  "implementation_sha": "10a1b9af293e6f4f4da20529e2dde9d1192a3525",
  "installed_previous_executable_sha256": "edc5260ff8272d7928d2db5f2988346bf4d388643febc0a8c2ee326790716aec",
  "packaged_app_executable_sha256": "e0c615f92a5975e313e25e7454002000a61da107530e421f64c6751e0ea2b9cb",
  "read_only_review": true,
  "schema": "mmx.codex_switcher_independent_review_packet.v1",
  "source_owned_path": "src-tauri/src/tray.rs",
  "test_results": {
    "frontend_pass": 13,
    "production_credit_switch_proven": false,
    "release_fixture_pass": 2,
    "rust_ignored": 1,
    "rust_pass": 86
  }
}
~~~

### Manifest content digests - SHA256SUMS.txt

SHA256: bab1489459e27e1d739e8272692a1671480cf0c7c181f7404c37e5fd17348b07

~~~text
50ea9398d88963da65d9a2c005df006d06dadbe3e34a6db5c94a3605f702a168  README.md
0b3a791e7fcdaf6ce968dd10bb9d46eb65b34cd51114af510190f094f4e088bf  EVIDENCE.md
c5e3545b5516527e36cde43ddc6e5e0219d399364cda688b9b42865d4d02dd78  REVIEW_RESPONSE_TEMPLATE.md
8e0d04c287578ed569f810d51375c56343be602dc620126677452af48cf29f8f  candidate-10a1b9af.patch
d462da91678736e472784d1f76871360c2237fb8ccc6dbce8c5b4a2f5246604c  guarded_release.py
ef647f7fc3e464b279d5f3435f72029658a21f7e234d98ce1f5ced62df95ad38  test_guarded_release.py
ab8fa5a7e432416ce45795a0c570a9cb125473c8291cc045e778e171a4bc5870  RELEASE_RUNBOOK.md
addbb5b47643adcdeef51970e8abf6a41f84e114969190f16f21cd062d34f8d0  MANIFEST.json
~~~