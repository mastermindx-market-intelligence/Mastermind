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
