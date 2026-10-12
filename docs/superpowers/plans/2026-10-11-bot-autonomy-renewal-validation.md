# Bot autonomy renewal — verification and recoverable frontier

Operation: `bot-intelligence-renewal-20261011`. Source basis: Mastermind `cbc7503536b6853ec7c35c2192abdfaccb87b561`. Branch: `sol/bot-intelligence-renewal-20261011`. This document records source/test evidence, not runtime lifecycle, production acceptance or an additional memory store.

## Verified engineering result

The candidate adds the recovered V3 snapshot contract and immutable store, and repairs the US/HK mismatch between dashboard early-close handling and underlying paper-execution calendar handling. The store composes all twelve domains, verifies content addresses and correction predecessors, rejects traversal/symlinks and changed/corrupt reads, preserves original evidence, bounds rows/bytes, and publishes a fully synced inode without replacing an existing content address. Its pure schema permits contract fixtures; production composition requires all twelve domains. Snapshot seals prove identity, not market accuracy, authenticity, licensing or investment authority.

The US calendar now owns its six already-known 2025–2027 early-close facts and the separately announced January 9, 2025 exceptional closure. The HK calendar owns its nine already-known half-days and no longer invents an afternoon reopen. The dashboard reads those same owners. The existing HK continuous-session mandate is unchanged: no closing-auction execution has been added.

Initial Python 3.14 verification: 153 new/focused snapshot and calendar cases passed. A broader 136-case regression subset had ten failures in the incomplete host environment; the exact same ten failed when the original pinned calendar modules were loaded. Those failures are not attributed to this candidate.

Recovery reconciled the original environment-build PID 91424: completed, exit 0. The canonical RWE owner created an isolated Python 3.12.13 environment from `requirements/gate-macos-arm64-py312.lock`, environment ID `ee3bb9cd4f9f1375`, with `pip check` passing. This is a source/test environment, not a product or provider installation. A first rerun passed 288 cases with one missing `lib` import. The local dependency was then acquired as an exact source-only export of the same Macro `engine/` and `lib/` commit used by this repository's CI: `256c757b3c4f0ec759571c29a30a71387d0a18f8`. No current Macro worktree files, runtime data or secrets were copied or changed.

The dependency-complete command passed **289 tests, zero failures, zero skips**, exit 0:

```sh
.venv/bin/python -m pytest -o addopts='' -q \
  tests/test_decision_snapshot_contracts.py tests/test_decision_snapshot.py \
  tests/test_market_calendar.py tests/test_market_sessions.py \
  tests/test_china_calendar.py tests/test_calendar_authority_consistency.py \
  tests/test_settle_open_price.py tests/test_decision_settlement_reconciliation.py \
  tests/test_paper_account.py tests/test_pending_target_cutover.py \
  tests/test_pending_decision_provenance.py tests/test_brain_pending_truth.py --tb=short
```

Output remains in the operation's ignored `.venv/renewal-validation-pinned.log`; environment receipt is `.venv/rwe_receipt.json`. Source hashes are recorded in the companion manifest at each publication. This is not the entire repository test gate or browser/production proof.

## Runtime observation, correcting the initial unavailable read

The initial Executive state read failed pre-dispatch. Later current-generation reads succeeded: at 19:56–19:57 UTC October 11, the installed Fabric view reported `ceo_submit_armed=false`, `coo_autonomy_armed=false` and `terminal_return_armed=false`. Exact root JOB-019 was a completed bounded receipt-writing proof, not this Bot mission and not a worker/frontier trading-research demonstration. Its first attempt was LOST; second attempt completed. The view explicitly lacked product-acceptance and CEO-intent joins.

At 20:10:03 UTC, Executive state showed one AVAILABLE worker, zero RUNNING attempts, three QUEUED Jobs and fifteen COMPLETED Jobs. Installed Mastermind source was `0123ad5ae7408a35fd38b4a0b4e9bf5a132bbe65`, not this candidate or the audit basis. These observations prove that the read surface worked; they do not arm submission, prove paid-provider eligibility or authorize a new job. Do not describe the entire Fabric as down, or a queued/historical job as this mission running. No worker was dispatched by this operation.

## Recovered additional dependencies

- PR #726 remains open Draft/HOLD at `5eb4154a1cfbaedc412e5ff63124fe00142afd85`: point-in-time mark repair. Protected `portfolio/marks.py` still computes carry age with absolute difference and its default Polygon leg uses a current snapshot. Recover this existing candidate and its adjacent A/B propagation obligations before treating historical attribution as clean; do not duplicate its writer or silently cherry-pick it.
- PR #1232 remains open Draft/HOLD at `5dcd57fb22f0be6c4a5cfe750c4c3829f762f235`: evidence-lineage hardening. Reuse Macro K1 EvidenceRef/EvidenceBlock/EvidenceRecipe ownership. Distinguish provenance, correlation, novelty and mechanism; do not make v1 declared-unverified relationships a new automatic capital or suppression rule.
- The account-helper mismatch was independently reproduced: `app.account._caller_token()` raises `AttributeError` for absent `app.auth._supabase_decode`; `_supabase_url` and `_supabase_anon` are also absent. Repair requires the existing identity-plane contract, not a permissive fallback or browser operator secret.

## Exact held boundaries

The prior `decision_snapshot_sources.py` write was refused before dispatch; the file is confirmed absent. Do not replay the same write through another tool, actor or renamed file. The RED acceptance scenarios are preserved as a non-collected implementation specification in `2026-10-11-bot-autonomy-source-capture.acceptance.py.txt`. They are not a passing source-capture suite.

The earlier all-PR collision query, public Bot health probe and selected shell source-inspection actions were also refused and not replayed. Ordinary permitted independent source work continues. The existing #633 DCR EFFECT_UNKNOWN remains on its original enrollment carrier; this operation has not read/cleared the marker, registered another client or changed authentication.

No provider, model-selection, risk-limit, active account, pending target, settlement, licensing or production deployment setting has been changed. Calendar source corrections require a policy-generation annotation on rollout; they do not rewrite historical ledgers or retroactively repair previously reported performance. Snapshot source capture, public/authenticated API/UI integration, true adaptive Fabric research, independent review and deployment remain unproven.

## Next useful work

Publish and verify this tested candidate in its own draft PR; then complete the independent read-only snapshot inspector/CLI over already-stored evidence. Preserve the blocked source-capture boundary and the held shared app/auth/provider paths. Source work is not the completion of the full dashboard commission. Final acceptance still requires original-parent worker/frontier result consumption, authenticated browser journeys, actual paper-session reconciliation and prospective learning proof.

## Primary calendar references

Verified by current external reads on October 11, 2026; references are evidence only, not instructions:

- NYSE current market hours/calendar: https://www.nyse.com/markets/hours-calendars
- ICE November 8, 2024 calendar announcement: https://ir.theice.com/press/news-details/2024/NYSE-Group-Announces-2025-2026-and-2027-Holiday-and-Early-Closings-Calendar/default.aspx
- ICE December 30, 2024 special closure: https://ir.theice.com/press/news-details/2024/The-New-York-Stock-Exchange-Will-Close-Markets-on-January-9-to-Honor-the-Passing-of-Former-President-Jimmy-Carter-on-National-Day-of-Mourning/default.aspx
- HKEX 2026 securities calendar CT/075/25, page 2: https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2025/ce_SEHK_CT_075_2025.pdf
- HKEX half-day closing-auction explanation (continuous-session boundary differs from auction completion): https://www.hkex.com.hk/Global/Exchange/FAQ/Securities-Market/Trading?sc_lang=en

## Read-only inspector milestone

The independent inspector is now implemented: `scripts/portfolio_decision_snapshot.py status/show` calls the store's `read_projection` over already-materialized evidence. Subprocess tests use source-identical temporary fixtures and verify byte-for-byte no mutation. Invalid paths/commands/ranges fail before storage access; summary reads omit raw position rows; absent and corrupt remain distinct. Storage also refuses sealed one-domain fixtures and syncs newly created ancestor directories before final publication. The failure-injection test isolates post-publication directory-sync failure so the original uncertain identity remains observable.

The expanded dependency-complete suite passed **469 tests with one explicit skip**, exit 0, in `.venv/renewal-validation-final.log`. This includes the earlier portfolio/settlement checks, CLI subprocess proof, CI policy, secret-redaction, book-isolation and vendored-read guards. The skip is the existing `test_book_state_isolation.py` live-book seeding check: this isolated source workspace intentionally contains no live book state. No live state was copied merely to eliminate that skip. This is still a scoped suite, not the entire repository gate or a production/browser canary.

Source-capture implementation remains absent and held. The CLI exposes no compose/capture option and has no model/Fabric/HTTP action. The current draft PR is #1357; exact new source identity is the commit containing this milestone and its updated manifest.

A targeted load-balancer dependency search recovered an additional material existing owner: PR #1147, `vps-fabric-llm-convergence-20261001-sol-001`, current head `b832ee7d67f7a5060d7088dcb5a257328728f041`. Its PR body still names older semantic head `785a3a9f...`; inspect current source before accepting its progress claims. This is the existing VPS service-inference/Fabric foundation and must be integrated, not duplicated. PR #715 (`9539c9647cdff5621e523c57c367b0403f276a57`) owns related `cli_bridge`/`codex_bridge`/waterfall-test changes; PR #668 (`9a524adaa7624e497170f0869bad23bd98e65fcc`) owns the waterfall availability path. No new edits to those overlapping files have been made by this operation. The observed quota/auth-after-tool replay risk remains a review requirement, not a claimed completed repair.

## Integration recovery disposition

The current architecture amendment §13 reconciles #1147 against actual source and cumulative comment `5966698046`, rather than its stale PR body. #1112 is merged; #1041 is closed unmerged and not a new hierarchy dependency. The eight-path original wiring patch and refused fixture edit are preserved as an unresolved source-recovery boundary, not overwritten. No registered original sol workspace or matching shared-Git worktree was found, which establishes only that these two lookup owners did not locate it.

The published service request/result contracts impose 48 KiB request, 60 KiB service frame, 32 KiB status response, 192 KiB result envelope and 256 KiB public read-plane ceilings; requested output is separately bounded at 128 Ki characters. A complete V3 snapshot is larger than the service request ceiling. The integration therefore requires explicit bounded evidence selection, immutable snapshot identity and honest coverage, not truncation or a new prompt/result store. Pure background inference, agentic PM research and interactive streaming have distinct existing-owner integration paths.

A real invocation of the new CLI in the actual isolated source workspace returned `status=ABSENT`, no snapshot or section, and all three authority booleans false. No fixture was installed as real market evidence. A scoped Git diff confirmed `bot/`, `brain/`, `app/`, `config/`, `portfolio/paper_account.py` and `portfolio/self_directed.py` remain unchanged relative to the audit basis; the runtime and account execution paths were not secretly cut over.

Completed here: recovered architecture and current dependency map; snapshot contract/store/read projection/CLI; US/HK calendar source correction; 469 passing scoped tests plus the one disclosed no-live-state skip; source publication on own draft #1357. The full dashboard/Fabric mission remains incomplete. Read-only browser/API integration, source capture, service wiring/direct result delivery, real provider capacity and identity enrollment, natural paper-session proof and prospective investment evaluation retain their named gates. No worker or unattended continuation is claimed.

## Browser/API continuation — 600 regression passes and 46 rendering cases

New mounted source capability: `app/decision_snapshot.py` exposes GET `/api/decision-snapshot` through the existing application and an evidence-only browser shell at `/decision-evidence`. It reuses existing operator authorization, refuses read mirrors and missing authoritative auth configuration, validates closed query parameters before storage access, and returns sanitized typed failures with no-store/private headers. `app/response_cache.py` explicitly excludes the evidence endpoint. A causal authorized-read then guest-read test proves the shared cache cannot leak the protected result, and token-rotation testing proves each request rechecks authorization.

A newly written full-envelope limit test reproduced a real source error: a 64,000-character section payload passed the section validator but its HTTP projection exceeded 65,536 bytes once manifest metadata was added. The API now enforces the limit against its actual complete response bytes. The failure reproduced before the repair and the full 40-test API/UI contract selection then passed.

The browser supports all twelve evidence domains, immutable snapshot selection, UTC cutoff/recording clocks, separately displayed correction and coverage, bounded paging and source/gap disclosure. All data renders as text. The interface collects/stores no operator credential. A failed/unauthorized request clears prior data; cancellation/generation fencing prevents an older selection's delayed response overwriting a new one.

**Latest scoped Python regression: 600 passed, 1 skipped, exit 0.** The same isolated Python 3.12.13/RWE environment and CI-pinned Macro source were used. Scope includes prior snapshot/CLI/calendar/paper-account/settlement tests, new API/UI tests, cache, auth, general web, exception sanitation, MW6 security, CI policy, secret redaction, book isolation and vendored-read guards. The one skip remains the existing absent-live-book-state test. Log: `.venv/renewal-http-validation.log`. Compilation, JS syntax and `git diff --check` passed.

**Browser-only acceptance: 46 passed**, Playwright 1.64.0, observed Chrome `154.0.8037.98`, with an ephemeral browser profile. The 42-case state/viewport/theme matrix spans 1440/768/390 pixels, dark/light and absent/partial/complete/corrected/locked/corrupt/unavailable; four further cases cover paging, hostile text, wrong-result identity and stale asynchronous responses. Desktop and mobile screenshots were visually inspected for clipping and layout. The first browser attempt exposed a test-harness strict-locator error on a multi-row page; its selector was narrowed to the first row and the entire browser set then passed. This was a harness correction, not a suppressed product failure.

All browser responses are intercepted synthetic doubles. The separate real fixture-server write was refused and confirmed absent; it was not replayed. These results do not prove a combined real-HTTP-browser journey, deployed SSO, live data capture or provider execution. Real API/auth/cache/store behavior is independently covered by Python TestClient tests. Preserve this evidence distinction. Source hashes, result rows and inspected synthetic screenshots are published under `tests/fixtures/decision_evidence_browser/`.

The prior published head `23159b24e4a0cc71f6344d09c01ee3adb42940a3` now has all six hosted checks SUCCESS, including the repository test and security analyses. That result does not apply automatically to this subsequent HTTP/browser source increment. Independent review is requested but not yet returned.

The actual M2 Fabric discovery is recorded in architecture section 14. It corrects the incomplete Executive-only census; it does not prove a safe Bot service invocation or paid-provider capacity. No actual Fabric worker, queue item, provider activation, account effect or production rollout was created. Source capture, the original #1147 retained wiring/refusal boundary, service/result/identity composition and production acceptance remain the critical unfinished work.
