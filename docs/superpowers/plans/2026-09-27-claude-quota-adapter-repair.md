# Claude quota adapter repair Implementation Plan

> For agentic workers: use superpowers:executing-plans, test first.

**Goal:** Close independently reproducible native model-selection and zero-capacity projection defects while preserving the existing three-window quota integration owners.
**Architecture:** Repair the existing Claude adapter and Capacity economics consumer. Macro Shared AI Provider Control remains the sole quota normalizer; no new allocator, ledger, account map, router or lifecycle.
**Tech Stack:** Python, existing pytest suites, native adapter fixtures only.
**Spec:** Existing #676 Claude fabric parity proposal plus the current 2026-09-27 Chairman assignment. This is a bounded delivery slice, not a replacement for #676/#7116.

## Global constraints
- Operation: claude-three-window-quota-repair-20260927-c3-001.
- Protected source/procedure: 3c35c5f8c4609c5bbaa4db424521facb6ad3757d; Skillpack 1.0.1.
- Preserve #919 admission, #999 remote-fleet, #1021 router, #676 parity, and Macro #7116 existing source/hold boundaries.
- No credentials, provider inference, paid credits, account rotation, production activation, merge or deployment.
- Direct execution: NO_ELIGIBLE_PRE_EFFECT_WORKER; Executive reader returned backend_unavailable. No substitute worker launch.
- Current user policy: protect Fable within the shared weekly budget; prefer exact Opus 5.5 for residual capacity; no Sonnet/Haiku workload routing.

## Review focus
- Moving/default/mixed-model selectors must not pass the exact-model contract.
- New exact Fable/Opus IDs must remain usable without hardcoded old-model substitution.
- A zero-start or zero-parallelism preview is not actionable capacity.
- Missing Fable-family telemetry never implies a free balance or permission to launch.
- Source tests and a requested review never imply live four-account optimization.

## Task 1: Exact native model selection
Files: control_plane/claude_worker.py; tests/test_executive_claude_worker.py.
Interface: existing ClaudeCodeWorkerAdapter constructor and _validate_exact_model; no public signature change.
- [x] Add failing constructor tests for fable, best, default, opusplan and case variants, before binary attestation or policy observation.
- [x] Preserve exact claude-fable-5-1 and claude-opus-5-5 positive controls using the existing typed observer fixture.
- [x] Repair the existing moving-selector exclusion; do not change route enrollment or silently rewrite a model.
- [x] Run the owning adapter suite and related broker/contract regressions.

## Task 2: Refuse non-actionable economic projections
Files: control_plane/capacity_economics_projection.py; tests/test_capacity_economics_projection.py.
Interface: existing project_quota_preference; retain schema and preview-only authority.
- [x] Add failing cases for zero estimated starts and zero suggested parallelism despite eligible_in_preview=true.
- [x] Refuse non-actionable capacity without changing upstream quota calculations or claim authority.
- [x] Run projection and adapter regressions, full repository test command, and diff checks; report dependency gaps honestly.

## Task 3: Existing-owner integration return
- [ ] Publish exact-head source and independent-review request through normal gates.
- [ ] Return the current four-account/Fable-first requirements and actual defects to #676 and #999 without transferring incumbent custody.
- [ ] Preserve Macro #7116 publication refusal; do not copy its unpublished repair.
- [ ] Record actual source/test evidence and exact next action in this cumulative source checkpoint.

MISSION_COMPLETE: false. Production three-window telemetry, identity binding, atomic reservations, account selection and natural-use proof remain outstanding.

## Ruling: model/runtime compatibility, same adapter scope

Fresh official Claude Code model configuration specifies Opus 5.5 requires 2.1.280 and Fable 5.1 requires 2.1.257. Merely accepting the exact model ID does not protect against an older installed harness. Extend Task 1 at the existing native construction boundary: reject these two known incompatible model/version pairs after binary attestation and before managed-policy observation. Preserve the independently reviewed allowed_versions requirement and all unknown-model/admission boundaries; passing a minimum is not support/entitlement proof.

- [x] Add below-floor, at-floor, above-floor and numeric-version-order cases using only the existing fake native executable.
- [x] Pin the existing exact-model positive controls to compatible fake versions, not the legacy 2.1.239 fixture.
- [x] Add the two documented compatibility floors to the existing provider-private adapter; no automatic update, model substitution, route enrollment or new model registry.
- [x] Re-run the owning regression campaign and record the changed-source result.

Primary reference, accessed 2026-09-27: https://code.claude.com/docs/en/model-config . This is version-compatibility source evidence, not a real-account or real-model canary.

Initial proof: 248 selected tests passed in 47.05 seconds before this compatibility increment. Full repository pytest stopped at collection: tests/mastermind_window_reader/test_mission_association.py imports integrations.business_mcp_auth.jwt_verifier, which fails with ModuleNotFoundError: No module named 'jwt'. No full-suite pass is claimed.

## Current integration findings and required owner inputs

The installed incumbent orch/fabric/pools.yaml has one Claude principal-seat entry with aliases claude-fable/fable, generic five-hour/weekly windows and descriptive historical quota notes. ext/pool_ledger.py labels Claude with one 5h window; the status projection does not establish four native account balances. Four realm directories are present, but neither directory names nor OAuth capability ordinals establish four independent enrolled subscription identities. No current per-account quota observations were obtained in this operation.

At protected 3c35c5f, the native adapter source exists but its descriptor is implemented=false. #919 remains draft/disarmed admission work; #999 remains draft pre-onboarding/fleet integration. #676 is a parity/quota specification, not live allocation. Macro #7116 at 4d7ddfd has existing Resource.applies_to, unobserved_holds and model reserves, with _balance subtracting other-model reserves and unobserved holds before each option's resource checks. This is the correct owner to extend; it remains a pure preview, and its current unpublished repair/refused publication must not be reconstructed through this branch.

The completion path must feed the existing owner three independently clocked native constraints per verified account: shared five-hour usage, shared weekly usage and Fable-family weekly usage. Every applicable constraint is enforced at the same existing atomic claim boundary, with provider resource/window/generation identity, bounded fresh observations, unobserved in-flight holds and no host-replica multiplication. Family telemetry missing/expired is UNKNOWN, not zero usage. Reset predictions do not mint a fresh balance.

### Fable-first reserve policy from the current Chairman assignment

Protect still-usable Fable capacity from interchangeable Opus work. Opus 5.5 is the preferred Claude residual model; Sonnet/Haiku are excluded from this workload policy, not silently selected through aliases or fallback. Qualified external economical workers handle routine work; suitable external frontier models absorb substitutable work when the Claude reserve would be violated. Existing task suitability and review independence remain hard gates.

For illustration ONLY, normalize a verified Max weekly budget to 100 units with a Fable cap of 50 in that SAME resource denominator. With total meter W and Fable-cap meter F, shared remainder is 100-W and remaining family cap is 0.5*(100-F). Reserve the required usable Fable portion of the shared remainder before considering Opus. After unobserved holds and safety margin, Opus residual is max(0, shared remainder - protected Fable - holds - margin). Actual acquisition must preserve native units; do not invent a token allowance from percentages.

Synthetic no-hold examples: W=0,F=0 protects 50 and leaves at most 50 for Opus; W=65,F=30 leaves 35 shared and 35 family, hence zero spare Opus; W=56,F=100 leaves no Fable and at most 44 shared for Opus, still bounded by five-hour capacity and pending consumption. The last pair matches the supplied screenshot but is not a fresh provider reading or authorization.

Reserve near-term five-hour capacity for queued/forecast Fable work as well; protecting the weekly quota alone can still starve Fable for hours. Prefer accounts whose Fable cap is already exhausted for residual Opus when their shared/short limits permit. Balance eligible Fable work across the other accounts using real reset times, pending holds and useful demand. Do not burn Fable merely to reach 50%; near-expiry reserve relaxation needs explicit bounded demand evidence, not a generic use-it-all score.

No account reassignment or job replay after START/EFFECT_UNKNOWN. Reconcile provider-observed usage against existing reservation generations to avoid double subtraction. No unapproved paid credits or API fallback: official noninteractive -p/Agent SDK Fable can charge usage credits without an interactive prompt. Account/billing eligibility must be proved before activation, not inferred from absence of a prompt.

Completion proof must include all four enrolled identities, missing-family/stale observations, five-hour/weekly/family exhaustion independently, Fable-reserve protection, reset/correction, two concurrent contenders for the last capacity, host replicas sharing a single subscription, denied Sonnet/Haiku routes, exact served model, zero unapproved credit spend and original-parent consumption of a real bounded task.

Primary references: https://support.claude.com/en/articles/15424964-claude-fable-models-on-your-plan ; https://code.claude.com/docs/en/statusline ; https://code.claude.com/docs/en/model-config . Checked 2026-09-27. Status-line docs expose five_hour/seven_day but do not document a Fable-family balance.

## Executed source evidence / publication checkpoint

- Original owning adapter + economics projection baseline: exit 0, 43.44 seconds (process 23498).
- Model-selector RED: 12 new case variants failed before source repair; old aliases and exact-ID controls passed (25761).
- Zero-capacity RED: both contradictory eligible previews failed to raise; seven controls passed (26657).
- Initial four-module GREEN: 248 passed, 47.05 seconds (27700).
- Known-model runtime-floor RED: six unsupported model/version pairs failed to raise; six compatible controls passed (37451).
- Final four-module GREEN: **258 passed, 49.61 seconds**, exit 0 (38405): test_executive_claude_worker.py, test_capacity_economics_projection.py, test_worker_adapter.py, test_claude_worker_preflight.py, with --noconftest -o addopts='' -q.
- Final full repository command python3 -m pytest -q --maxfail=1: collection stopped at test_mission_association.py because jwt is not installed (43028, exit 1). This is not a full-suite pass. No dependency or test assertion was removed to hide the failure.
- One earlier verification command named #999's unmerged test_native_claude_remote_fleet.py; it exited before running tests because that path is absent on this base. The corrected owning-suite list above does not import or claim #999's coverage.
- git diff --check and four-file Python compilation: PASS (42586).
- Protected master advanced to 90402d76494707ca4d385076a007b2de78d23a20. Its six changed paths concern Linux worker deployment and tests; all four changed code/test paths here and AGENTS/Skillpack are unchanged across that movement. No ancestry-only merge or unrelated source import was made.

At this file's commit boundary, normal source publication and independent review are still pending; the PR receipt will carry the resulting exact immutable head. All native provider/account/login/credit/Runtime activation effects remain NONE. This operation has not started a child worker or watcher. The existing #999 integration owner retains Runtime/fleet source custody; #676 and Macro #7116 retain quota/parity ownership. This source slice does not unblock any held production gate by itself.

FINALIZATION_CLASSIFICATION: CHECKPOINTED_CONTINUATION
MISSION_COMPLETE: false
Next exact action: publish this tested native-adapter/economics-consumer slice for independent review, return the four-account/Fable-first inputs to #999/#676/#7116, then integrate through existing native admission and Provider Control owners. Live completion requires fresh per-account three-window observations and actual claim/usage/parent-consumption proof, not another static specification.
