# BytePlus Personal Pro — post-review source preflight and canary gates

**Scope:** implementation follow-up to original [PR #1725](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1725) at immutable reviewed/CI-green source head `1d3304d33a35f0c09865387fe268826cc2a1d7f4`. This follow-up is a **separate branch** and does not change the original branch or PR. Neither branch represents an installed BytePlus service, a live worker, or commercial inference entitlement.

## Deterministic, offline checks

From this follow-up checkout, with the existing repo test environment:

```sh
python -m scripts.byteplus_coding_plan_preflight
python -m pytest -q tests/test_byteplus_coding_plan_preflight.py tests/test_capacity_economics_projection.py tests/test_subscription_harness_bindings.py tests/test_fabric_attended_claude.py
```

The preflight imports only the existing **source catalog, Model Router, reviewed adapter descriptor, and activation blocker functions**. It creates no queue, worker, credential, account, lease, provider watcher, secret file or independent admission controller. It never queries Keychain, shell execution, BytePlus network APIs, personal CLI state, quota or host health. Its report is intentionally `SOURCE_ONLY`, not an Executive receipt. This is a preflight diagnostic, not a registration command; do **not** interpret a true source catalog validation as an authorization to start.

Source-only facts (expected under the held profile):

- Profile/binding: `byteplus-coding-plan-personal` / `byteplus-coding-plan-personal.claude-code-anthropic`.
- Exact subscribed coding-tool endpoint: `https://ark.ap-southeast.bytepluses.com/api/coding` (NEVER `/api/v3` general PAYG). Codex `/api/coding/v3` is a separate not-yet-reviewed Responses binding; this script does not enroll it.
- Seven explicit source roles: routine and subagent `glm-5.3-flash`, fast `dola-seed-2.0-lite`, hard `dola-seed-2.0-pro`, backend `deepseek-v4.1-flash`, frontend visual `dola-seed-2.0-code`, exceptional review `deepseek-v4-pro`.
- Actual binary/process proof is **not** observed. The deterministic unit test compiles safe **synthetic** binary/spec fixtures through `prepare_attended_claude_launch` for every role, checks no secrets in the frozen descriptor, fixed endpoint, fixed model, retry=0, and `preparation_only=true` / `start_authorized=false`. Synthetic fixtures are not provider-origin credentials, host runtime attestations, or real START.
- Current held source/descriptor status: `SPEC_ONLY`, generic attended adapter not implemented, no enrolled BytePlus realm, no Capacity fact/available quota slots, no observed account-specific model-response/usage debit, disarmed Model Router alias `byteplus.attended`. Even falsely asserting other gates true cannot override `implementation_not_built`, `implementation_not_proven_live` or `source_policy_disarmed`.
- The canary-admission test calls the existing `issue_provider_realm_enrollment_receipt` and `export_capacity_owner_fact` under **isolated test-only owner-seal fixtures**, then calls the real admission factory with actual BytePlus catalog data. `SPEC_ONLY` is still rejected. This demonstrates factory-gate enforcement against even correctly sealed **test** facts, **not** that BytePlus has real owner-enrolled production receipts.
- The separate quota readback projector only validates caller-provided official management JSON, reports whole used percentages, strips private viewer/account fields, and intentionally leaves startable jobs and concurrency `null`. Rounded 0% is **not** a zero-request count or proof of usage debit.

## Supported-tool attended canary — exact future ceremony, NOT executed here

Only the actual subscriber on an approved, individually attended **Claude Code** tool session may test the personal subscription. Do not use custom raw API traffic, generic background Fabric inference, a batch runner, shared account multiplexing, cross-subscriber use, scheduled service, or the distinct ModelArk PAYG endpoint to complete this proof.

1. The subscriber/credential owner confirms the existing isolated Claude Code Coding Plan profile and account. Do not copy or print credential bytes into source, shell history, logs, PR comments or chat. Confirm the client is supported by BytePlus for the subscribed account, its exact `/api/coding` endpoint and selected exact model. A local `claude --version` alone is not canary proof.
2. From the **approved provider-management control plane**, collect a redacted pre-canary account tier, subscription state and quota-window observation with provider observation timestamp. Preserve the original private owner record; no identity/secret in GitHub. Do not treat a management readback as worker identity or permission.
3. With the real user in attendance and the supported client, execute one bounded coding task with a known deterministic result and explicit model. Capture the returned served model, terminal result, reviewed tool behavior, request completion and independent test of the artifact. A user saying “done” is evidence of a ceremony, not provider transaction attribution.
4. Collect a post-canary management observation from the same account and window. A provider-reported request delta, attributable transaction or equivalent authoritative measure is needed for quota-consumption proof. **0% → 0%** is inconclusive because the vendor reports whole percentages; do not invent per-model weighted requests or a concurrency number.
5. Stop if plan terms or provider messages indicate unsupported use, access denial, separate PAYG billing, wrong account/model, throttling, credential problems or uncertain task effects. Preserve original attempt identity; never silently reroute or replay after START.
6. Only after a reviewed real-path result and entitlement may the **existing** ProviderRealm and Capacity owners issue their own typed, account/host/model-bound facts. No user-provided booleans, CLI text, raw dicts, or a source preflight can mint those receipts. The existing canary factory currently **refuses `SPEC_ONLY`** even if typed owner facts are simulated, so a source-qualified implementation/release is still needed before any broker claim.

## Production-admission decision table

| Gate | Current proof | Required successor evidence/owner |
| --- | --- | --- |
| Exact source/harness identity and model roles | Source tests PASS | Preserve checked commit and catalog digest |
| Independent source review of original head | Fabric review accepted (source-only) | This follow-up must be independently reviewed on its own new exact SHA |
| Full current-head CI | Original #1725 green | Follow-up exact-head CI before any merge |
| Binary, isolation and attended model result | Not proved by source-only test | Supported-tool execution owner, exact real-path canary |
| Account-bound subscription tier/usage | Earlier CLI reported Personal Pro Running, integer 0% | Provider-control owner: fresh attestation, response/debit attribution |
| Hosted ProviderRealm receipt | Not issued here | Existing realm owner, exact binding/account/host and generation |
| Capacity available slot | Unknown | Existing Capacity owner, typed current fact, verified quota/window |
| First-lawful-tier eligibility | Disabled by reviewed Model Router | Release-owner-approved scoped model/harness policy only |
| Worker launch and post-START reconciliation | Not performed | Existing Executive/Fabric broker with lease/effect proof |
| Automated shared inference through Personal Pro | **Not permitted by source use policy** | Different commercially authorized account/API product + review |

**Do not force a production start to satisfy an implementation checklist.** An individually attended coding-tool subscription may be useful without ever becoming an unrestricted autonomous Fabric pool. Separate commercial API rights, independent security/review, source release, capacity binding and production-path proof remain distinct gates.

## Follow-up review fixes and regression falsifiers

1. The economic preview is untrusted. The follow-up treats case-folded, ASCII-separator-normalized identity strings containing `byteplus` as **non-actionable** regardless of surrounding prefixes/suffixes or forged positive worker counts. Previously passing disguised names (including `BytePlusTrusted` and `mybyteplus.attended`) now fail, while unrelated preview providers retain their original source behavior. This intentionally fails closed even for future BytePlus commercial aliases until an independently reviewed entitlement-bound owner exists.
2. The independent Anthropic Coding Plan binding endpoint literal was previously redundant with `endpoint == profile.base_url`. A new mutation-discriminating test deliberately substitutes a corrupted in-memory profile **and** override with the same wrong PAYG endpoint; the literal independent anchor still rejects it. Removing that literal would make this exact test fail. The production profile validator remains untouched.

## Non-goals and rollback

No changes to PR #1725, its accepted Fabric review, CI-green source head, existing MiniMax finite identity, Qwen 429 repair PR #1731, quota router PR #1441, host fleet config, credential store, installed picker, lease queue or production workers. All effects in this follow-up are source files/tests on a new Git branch. Rollback is abandoning the follow-up branch/PR; no runtime state restoration is needed.
