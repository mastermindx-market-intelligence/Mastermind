# Manual pool/model selection for Subagent Fabric — source candidate

**Chairman directive, 2026-10-21.** Existing auto routing remains default; an originating session may optionally name a qualified provider pool and an exact model where special intelligence or capability is needed. A pinned Grok request must never silently execute on GLM. Grok 4.7 is an example **not a claim of live provider readiness**, capability entitlement or model quality proof.

## Canonical state

- Executive OS plan-v4 already supports manual placement and fail-closed model pins, with tests in `tests/test_executive_coo_ready_frontier.py`.
- Native `fabric_task.py request` has `--pool/--model`; actual picker currently restricts exact models. [PR #1365](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1365) carries the narrower default-qualified exact-model/preview selector, is open DRAFT/HOLD and not installed. Installed M2 generation differs from that patch's historical preimage (see #1365 issue comment 6287191803).
- The current Web Fabric-only tool `fabric_request` rejects all model/pool fields. Its original source owners have concurrent drafts [#1438](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1438), [#1457](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1457), and [#1536](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1536). Therefore this branch proposes **a non-mutating patch file plus source replay test only**, not a competing modification to their live paths.

## Contract

- Caller may omit routing fields (AUTO), choose `pool` only (POOL), or choose `pool+model` (EXACT_MODEL). Closed provider values, literal model tokens; no arbitrary host/CWD/shell/account or permission widening.
- Before creating any controller for manual requests, the same original `fabric_task.py preview` must return matching `PREVIEW_ONLY/reserved:false`, run ID, provider pool and exact model if requested, using the caller's real classification, review-independence and escalation reason. Any preview unavailable/mismatch rejects `MANUAL_ROUTE_UNAVAILABLE` without submitting work.
- At request, forward exact `--pool/--model` to the existing native picker and **disable automatic cross-provider quota continuation for manually selected routes**. Picker/lease/host/identity guards still recheck on actual launch and may refuse; a preview does not reserve capacity.
- The unchanged `fabric_capabilities` tool reports manual availability only when the native adapter's help advertises `preview`.
- Failures, stale admission, no capacity, permission denies and uncertain modifying effects remain distinct; no replay, retry, alternate carrier or new lifecycle/Capacity owner.

## Proof / release gate

`tests/test_web_fabric_manual_model_patch.py` enforces exact current Git blob preimages, applies the candidate patch only in a disposable directory and runs the entire original Node facade suite with new synthetic negative/positive manual-pin tests. These tests DO NOT prove real Grok-4.7 availability, vision entitlement, transport adoption, real worker START or parent acceptance.

**Do not merge or hot-apply to the installed source.** Existing Web backend owner must reconcile this patch with #1536 result paging, #1566 modern gateway, the actual installed selector/release from #1365, current native provider model catalog and distinct per-model capability/quality gates. Require source-owner admission, exact-head CI, independent review, a safe immutable service release and one origin-session pinned-model START->result->parent consumption->accepted proof. Before any Grok-4.7 canary, verify current provider-native catalog actually exposes Grok 4.7 in an entitled, admitted pool. Unknown is not available.

At this boundary: **BUILT_NOT_PROVEN / MISSION_COMPLETE=false**, no host or provider effects performed. Source baseline `230e9a301ed774e79410829f1b5c049226fa59f1`.
