# OpenCode Go composition checkpoint - 2026-09-14

## Mission and status

Preserve one coding agent's model, local transcript, completed tool results and workspace when an eligible capacity member is exhausted. Capacity selection must not restart the agent, repeat completed tools, or fabricate quota. This checkpoint is PARTIAL / BUILT_NOT_PROVEN / PRODUCTION-INERT, not final acceptance.

Procedure: protected Mastermind `51b815ab9527e15c9218b049f622dc4d3e0bfbc4`, compatible Skillpack 1.0.1 / bootstrap major 1. Current Chairman continuation supplied source-work intent. This document does not grant a runtime or provider-policy exception.

## Exact source carriers

| Component | Carrier | Tested implementation |
|---|---|---|
| Account-shared usage composition and selector | Macro #7142, `sol/opencode-go-pool` | `814e6d4e6aaa13d27f9302febf954a780923db6c` |
| Go usage acquisition/parser | Macro #7143, `sol/opencode-go-subscription-usage` | unchanged `d8127bded3a9a35bc501e786d27fa32f0ecdd923` |
| Request custody and transport kernel | Mastermind #622, this branch | `f68fc0c62552bfd4a4994792698e7064899d008f` |
| Cross-repository synthetic proof | Mastermind #622 | `a2a529e6d633b2e6aa522b294d531fa4db525de0` |

Parent #583 is concurrently owned and advanced beyond this branch's original base. Its latest observed body names `5b737661f8e861b1000e88f15bd36f728ccd26af`; do not overwrite its credential/ACL work, merge merely for ancestry, or treat this isolated result as latest-base compatibility proof. #7143 remains stacked on #7103. No carrier was merged or armed.

## What changed

The real Go parser normalizes percentages to floating-point values, but the old selector accepted only integers. The new account observation bridge consumes existing `quota_rows`, preserves fractional values, requires account-shared allocation scope, rejects duplicate/mixed-time rows, and makes missing windows unknown. An exhausted provider status dominates an available display label even when the percentage is inconsistent.

Selection accepts an explicit decision clock and request exclusions. Excluding A after quota refusal no longer rewrites the membership hash; unknown, expired, future-dated or stale evidence cannot become renewed capacity. Pool membership hashes are validated, not trusted as caller assertions. They still do NOT establish rotation-safe enrollment identity or independent purchased entitlements.

Transport validates and freezes request bytes before callbacks. The model, transcript and session cannot change between members. Alternate authentication headers, cookies, hop-by-hop headers and billing-source overrides are not forwarded. Default object representations exclude headers and bodies; ordinary outward tracebacks suppress underlying callback messages. Account-scoped Responses references are rejected for rollover; canonical local context must be supplied instead. Function parameter schemas are not mistaken for opaque remote state.

Generic AuthError no longer rotates. OpenCode's published handler uses that type for both invalid credentials and blocked workspaces. Only a complete structured GoUsageLimitError with a recognized quota horizon is a candidate no-effect refusal; deployed gateway behavior remains unproven. Network ambiguity never rotates. Reaching the configured attempt budget is distinct from proving the entire pool exhausted. Callers may supply an expected pool generation across requests.

## Executed evidence

A Linux sandbox with Python 3.13.5 / pytest 9.0.2 executed exact source copies. Starting copies were checked against Git blob identities. Published implementation/test blobs were then read back and matched the tested bytes.

- Pool original plus regression tests: **36 passed**.
- Transport original plus safety tests: **41 passed**.
- Cross-repository parser/selector/transport tests: **7 passed**.
- Combined run: **84 passed**; compile check passed.

The new adversarial checks against the old source produced 15 failures / 2 passes before repair. That is NOT a claim that the old original unit suite failed.

`docs/evidence/opencode_go/test_cross_repo_composition.py` executes the actual Go usage acquisition function with an injected fake HTTP getter, actual usage parser, actual account bridge/selector and actual transport kernel with a fake sender. Three logical turns succeed on A, B and C; wire attempts are A, A/refused, B, B/refused, C. A single test process, temporary workspace marker, accumulated tool-call/results and session ID remain intact. Replay request bodies are byte-identical. This proves software composition and custody, NOT actual model recall, a running coding agent, real account independence, live quota or provider execution.

The same proof covers missing weekly readings, fractional percentages, inconsistent exhaustion, reset requiring fresh provider evidence, generation drift, and all-members-exhausted refusal before inference.

For reproduction, assemble a disposable offline import fixture using the exact files at the pins above: Macro `engine/provider_account_pool.py`, #7143 `engine/provider_subscription_usage.py` and `engine/provider_subscription_usage_opencode.py`, plus Mastermind `control_plane/opencode_go_pooled_transport.py`. Copy the four repository test files and this proof file. Do not assume either Macro branch alone contains both pending changes. Set PYTHONPATH to those two fixture roots and run pytest on the explicit tests. This is an offline test fixture, not a production import adapter or workspace-custody bypass. Full repository CI, independent review and native macOS integration were not run here.

## Ownership and no-rebuild boundary

Model Router owns suitability. Macro Shared Provider Control owns account/quota/health observations. Capacity Fabric and Executive retain atomic allocation and Job/Attempt/Worker authority. The kernel owns no persistent account registry, quota ledger, retry controller, transcript or worker lifecycle. The `SyntheticProvider` in the proof is a test fixture only. No v1 capacity or placement schema was widened.

Calling credentials pool members does not by itself amend post-START carrier law. Production requires a reviewed binding that identifies exactly which memberships, enrollment revisions, model/protocol and existing authority permit the request. A self-asserted membership hash is insufficient.

## Gates and exact remaining work

1. Review and reconcile source carriers with current #583/#7103 without overwriting their owners. Current PR prose predates the auth-classifier correction; source plus this checkpoint records the narrower behavior.
2. Define the rotation-safe enrollment/resource binding through existing owners. The usage API does not return a durable identity witness; three keys or three zero-percent screens are not evidence of three independent entitlements. Preserve revocation, replacement and plan-generation invalidation.
3. Implement a streaming sender and worker-private harness binding, with authenticated local access, bounded cancellation and no replay after stream output or ambiguous acceptance. The present kernel buffers complete responses and is NOT a localhost proxy.
4. Connect refusal/reset/health observations and concurrent reservations to the existing Provider Control/claim path. The pure selector does not reserve capacity and cannot prevent simultaneous workers oversubscribing the same allowance.
5. Only after applicable enrollment, usage policy, runtime and tool gates pass, perform a bounded real supported coding-agent task and demonstrate its visible result. First prove one account. Any approved pooled rollout then needs real identity, same-model continuity, streaming, cancellation and concurrent-allocation proof. Leave paid overflow off unless separately budget-authorized; keep training-enabled models outside proprietary workloads.

The native MacBook workspace inspection in this turn was blocked by the platform. It was not retried on another device or carrier. No keys were read, enrolled or copied, no provider calls made, no services installed and no workers launched. The three registrations remain Chairman-reported; runtime enrollment is UNKNOWN.

OpenCode Terms effective Aug 15, 2026 explicitly prohibit multiple accounts used to circumvent limits or suspensions. Registration and acceptance of ban risk do not satisfy the existing `usage_policy_satisfied` gate. Preserve that unresolved gate rather than marking it green. Supported single-account work can be separated from any provider-approved pooling arrangement.

Sources: https://opencode.ai/legal/terms-of-service ; https://dev.opencode.ai/docs/go/ ; `anomalyco/opencode@df23b7f9488a38e6f8064a0739d4f8cde86d7cfb`, `packages/console/app/src/routes/zen/util/handler.ts` and `packages/console/app/src/routes/zen/go/v1/usage.ts`.

No Fable/worker assignment or watcher was created. Sol retains acceptance. Next capability: a reviewed single-account streaming harness binding, while the enrollment/claim/policy requirements above remain explicit gates for a real pool.
