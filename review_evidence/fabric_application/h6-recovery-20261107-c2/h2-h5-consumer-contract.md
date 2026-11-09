# H2 to H5 consumer contract — existing owner projection

Programme #983, original final carriers Mastermind #2175 / Macro #10740. This document specifies the read join owed by the assigned integration. It creates no endpoint, account registry, refresh service, grant or UI authority. Current OS source is PR2109 head `4fd801e48cd3b4c6f506fd60bc5f7fc8d50b4c6e`; its stale PR-body head is not used as the source identity.

## Producer, consumer and authority

H2 source `69ead1bdc1b7f6e1b62ef186d955d07cbd718dce` supplies `account_quota_view` in `ops/native_fabric/grok47/quota_billing/quota_remote.py`, SHA256 `91c89d4197d791a078e804db9c591c4cddc197f1e35f54f46fba95fe7b27a9a5`. The same bytes are emitted in the complete H2 native generation. This projection evaluates quota evidence only. It never evaluates model/workload entitlement, no-overage, execution budget or admission.

The existing GLM/MiniMax refresh owners own observations and failure lineage. The GLM cache-only adapter is `cached_glm_account_view`; `qualified_provider_view` can perform an on-demand provider refresh and is not a passive view function. Do not call it from a route promised to have no provider effects. The existing GoRouter owns Go refresh and its store; H2 does not provide a second Go live reader.

The OS consumer remains its authenticated Workspace App → App-peer → Executive service → WorkspaceReadService chain. Its current `GET /workspace/resources/models/current` describes logical model configuration and explicitly retains `physical_account_pools=NOT_JOINED` / `live_capacity=NOT_OBSERVED`. A physical-capacity extension must pass through that existing closed-wire owner and its current principal/permission/expiry fences. Preserve its logical model revision separately from observation/configuration generations. A raw cache dump or browser-held key is not an acceptable join.

The existing Fabric `/application-pools/view` requires an authenticated enrolled service and explicit `admin_pool_view` permission before returning metadata. Any physical-account extension must also intersect the original service's allowed pools/accounts and role scope. The frontend must not broaden this authority or infer it from an account name, configured alias or percentage. A missing join remains unavailable.

## Exact H2 dictionary contract

The returned dictionary has these fields. This is documentation of the existing helper's output, not a replacement wire schema.

| Field | Type and meaning |
| --- | --- |
| provider, account | Provider name and original local account alias. Neither independently attests physical provider identity. |
| allowance_scope, account_generation | String or null. Optional original-owner physical/shared-window binding; null is unknown. |
| config_generation | String or null. Current original configuration revision, distinct from physical account identity. |
| endpoint | Validated public HTTPS endpoint or null; no key, user info, query or fragment. |
| windows | Every applicable provider window exactly once. GLM and MiniMax require 5h plus weekly; Go requires 5h, weekly and monthly. |
| refresh_error | Original refresh failure or null. A failure cannot be cleared by deriving a new view. |
| failure_config_generation | Original failure binding or null. Preserve refusal across changed configurations until reconciled. |
| quota_ready | Boolean conjunction of qualified evidence for all required windows on this one account. It is not permission to run. |
| entitlement, no_overage, admission | Literal `NOT_EVALUATED` in this helper. Do not render these as allowed. |

Every window carries:

| Field | Type and meaning |
| --- | --- |
| window | Original required window identifier. |
| remaining_pct | Number from 0 through 100, or null. This is not an integer token/request budget. |
| reset_at | Original valid ISO timestamp or null. |
| observed_at | Original producer timestamp or null; never replaced by the UI's read time. |
| source | Original provenance, including PROVIDER_AUTHORITATIVE or UNKNOWN. |
| age_s | Age from the original producer clock, or null when invalid. |
| confidence | Original validated value or 0 for invalid/unknown input. |
| units | Original units label; percentage views do not establish native meter quantities. |
| reset_state | UNKNOWN, DUE or FUTURE. A null clock remains UNKNOWN. |
| ready | Whether this window passes the helper's evidence rules. |
| reason | Null only for a qualified window; otherwise the first applicable refusal below. |

The current freshness limit is **600 seconds**. The separate original refresh cadence is **300 seconds**. These values govern different questions; observing a cached row does not refresh it.

## Unknown and refusal behavior

The helper evaluates errors in a defined order. Preserve the returned reason instead of inventing a successful fallback.

| Reason | Consumer meaning |
| --- | --- |
| REFRESH_FAILED | The original observation attempt failed; retain the failure. |
| WINDOW_MISSING / WINDOW_AMBIGUOUS | Required complete-window evidence is absent or duplicated. |
| CONFIG_GENERATION_UNQUALIFIED | Current configuration binding is absent or differs. |
| ENDPOINT_UNQUALIFIED | The public endpoint is absent, invalid or mismatched. |
| ACCOUNT_GENERATION_CHANGED / ALLOWANCE_SCOPE_CHANGED | Original account/shared-scope binding changed. |
| NON_AUTHORITATIVE / CONFIDENCE_INVALID | The data cannot establish authoritative current allowance. |
| OBSERVATION_STALE_OR_INVALID | Original clock is absent, invalid, future or older than the accepted bound. |
| RESET_INVALID / RESET_REQUIRES_OBSERVATION | Clock is malformed or the prior window is due; passing the clock is not replenishment. |
| BALANCE_UNKNOWN / EXHAUSTED | Remaining percentage is unknown/invalid or zero. |

Display observation age and reset provenance even when an earlier binding refusal is the primary reason. Never synthesize a countdown from a null reset, infer unlimited capacity, join one account's weekly window to another's 5h window, or count aliases/models as independent wallets. Keep account/global/model/workload constraints as separate original-owner facts.

The UI may show historical percentages with an explicit stale/unqualified state. Controls that perform refresh, reset, key rotation, enrollment, policy publication or admission remain under their original separately authorized owners; this read dictionary grants no such control.

## Representative real sanitized observation

`h5-historical-derived-view.json` was generated by the **actual emitted H2 helper** from the genuine original refresh receipt at:

`docs/evidence/hermes-pool-h2-original-refresh-reset-2026-11-07.json`
at H2 commit `69ead1bdc1b7f6e1b62ef186d955d07cbd718dce`,
receipt SHA256 `d0e2543185f8c4af72396e41bef7f1351de8a93928f8f0d76c9a04a75ba024cd`.

The producer observed GLM at 12:03:21 UTC and MiniMax at 12:03:18 UTC. This sample preserves those clocks, the real percentages and the null GLM 5h reset. Local account aliases are replaced with stable sample labels. The two labels are not a claim of two independently qualified physical accounts.

The receipt did not retain endpoint/configuration/account/scope binding, confidence, exact integer capacity, entitlement or budget evidence. Those values are left unknown; confidence is conservatively unqualified. At the recorded 14:48:11 UTC assessment, both sample accounts are stale, `quota_ready=false`, and entitlement/no-overage/admission remain NOT_EVALUATED. The primary helper refusal is CONFIG_GENERATION_UNQUALIFIED. No provider call, credential read or runtime state write produced this sample.

This receipt proves original natural GLM replenishment from 99% to 100%. It does not prove an exhausted-account recovery, card redemption, current readiness or APPLICATION admission. This historical sample must not be copied into live quota state.

## Remaining joins and acceptance

The assigned integration owns the following source and runtime joins:

1. Extend the existing authorized OS read path with the exact derived dictionary and closed schema, preserving per-role/account filtering and explicit missing-source states. A UI-only fixture cannot close the backend join.
2. Extend existing GoRouter observation projection with its original successful `snapshot_at`, endpoint/account/configuration binding and failure lineage for rolling/weekly/monthly windows. Its current status exposes snapshots and last error but omits that observation clock. Preserve the original Go401 denial; no alternate request or second poller.
3. Retain H3 as unqualified until actual upstream integer quantities, physical/shared membership, settlement coverage and consumption enforcement exist. The separate H3 counterexamples show why this H2 read dictionary is not an admission envelope.
4. Provide H4 an actual qualified account/product/model/endpoint/workload and its enforceable no-overage or hard-budget boundary. Current percentage samples, configured max_steps and a budget reference do not prove total billable consumption.
5. Prove the authenticated browser journey with original clocks and real owner state after authorized release, including sign-out, source invalidation, stale/missing/failure/null/reset-due evidence and only the controls actually permitted to that role.

Current source readiness is distinct from backend activation, actual account authority and installed/browser acceptance. The first separately qualified Hermes primary/tool slice remains independent of the unqualified expiry optimization and the broader OS completion.
