# Kimi Ultra routing and capacity protection

## Purpose

Use the two existing Morph Ultra subscriptions for eligible Kimi work while keeping their independent sustained token budgets intact. Before this change, `auto` excluded Kimi, a sibling route's cooldown could divert requests away from a healthy subscription, and estimated output reservations could admit more output than the subscription could sustain.

This implementation extends the existing router, admission window, route circuits, configuration reload and observability. It does not add a dispatcher, queue service, credential store, provider account or background scheduler.

## Subscription policy

Each independently entitled Kimi subscription has a configured sustained budget of 24,290 uncached input tokens and 6,162 output tokens per minute. The operating fraction is 0.9, giving 21,861 input and 5,545.8 output tokens per minute, with one in-flight request per subscription. Multiple API keys are not evidence of independent entitlement.

Strict routes reserve the complete effective output ceiling before sending. Routing aliases may cap that ceiling at 4,096 tokens, exposed through the requested/effective output response headers. Exact-model requests retain their requested ceiling. A request that cannot fit is ineligible for that resource; existing explicit overflow policy still applies. Long prompts are not truncated to force eligibility. Advertised burst reserves are not treated as recurring sustained capacity.

The rolling local window is an estimate, not a provider balance. Morph's authenticated response headers may reduce admission allowance or observed limits. Output headers describe capacity before the response completes, so outstanding output reservations are subtracted. Missing, malformed or stale headers cannot grant additional allowance. Cache credit requires observed usage; the first matching prefix receives no speculative credit. A per-conversation `x-session-id` improves cache locality without pooling unrelated conversations.

References: https://docs.morphllm.com/ultra-plan and https://docs.morphllm.com/sdk/components/caching . Provider limits remain external facts that may change; resource configuration and provider observations determine runtime behavior.

## Selection and fallback

- `auto` includes DeepSeek, Kimi, GLM and Qwen with initial weights 6:3:1:1 and capacity-aware weighted selection.
- `fabric/balanced` uses GLM, Kimi and Qwen with weights 4:4:2 and capacity awareness.
- `fabric/kimi-preferred` keeps Kimi first, then its existing qualified GLM/Qwen alternatives.
- `fabric/fast`, the explicit frontier tier, exact-model route allowlists, metered fallback restrictions and existing explicit overflow policies retain their roles.

Model weights are preferences when a resource is eligible, not traffic quotas. Measured headroom and current in-flight work reduce selection pressure. Existing session affinity is preserved when it remains eligible. A cooling sibling subscription cannot suppress a ready subscription. Only known pre-effect failures can use bounded fallback; partially delivered or uncertain requests are never replayed.

## Continuity and observability

`admission_state.py` persists the existing admission owner's rolling charges, active reservations, provider observations and route cooldowns through an atomic, owner-only file. Clean restarts restore recent charges. Interrupted active requests retain a conservative resource hold through the upstream uncertainty window. A first install with no prior ledger waits one rolling minute before strict Kimi admission. A corrupt or unwritable ledger fails closed for strict resources and reports the error; unrelated routes remain available.

Checkpoint I/O runs outside the request event loop. One writer serializes immutable snapshots and coalesces routine updates, while strict Kimi admissions wait for their own reservation revision to become durable before sending upstream. Cancelling that wait cannot cancel the disk writer or replay a request. A failed write latches an error instead of creating a retry storm. Graceful shutdown flushes remaining changes. This is necessary on the M2, where measured synchronous checkpoint writes took approximately 0.45 seconds each.

`/routingz` reports configured and effective caps, charged/reserved input and output, in-flight occupancy, remaining headroom, provider observations and freshness, recovery holds, persistence health, profile weights and effective request ceilings. These diagnostics distinguish local estimates from upstream observations. The source manifest includes the admission-state module and measures the actual runtime source.

## Direct M2 rollout

The deployment authority is the Chairman's direct request of 2026-11-13. Protected source-law pin: `c0b30b422d2310e614f91faed49a4adbce4291f0`. Baseline is the actual M2 release, including its existing local overlays; it must not be replaced wholesale by an older repository version.

Use the incumbent reload lock, exact source/config preimages and backups. Temporarily disable both Kimi routes for new admissions and verify adoption before changing source. Keep them disabled through the graceful SIGTERM and launchd replacement. Do not run overlapping serving processes with independent admission windows, and do not force-kill active streams. Verify the replacement PID, source generation, manifest, configuration and persistence before enabling the promoted profile. New admissions can pause while the old process drains; this is not a zero-downtime rollout.

The source archive branch preserves code and evidence without making direct M2 activation wait for a PR. Production installation, source archival, test success and real request proof are separate receipts, recorded on Mastermind issue 983.

## Validation

The focused regression suite covers whole-output reservation, exact ceilings, shared resources, sibling isolation, header semantics, cache estimates, partial-stream failures, no-replay behavior, malformed cooldowns, active configuration changes and clean/crash/corrupt/cold-start recovery. Existing wire, model-tier, overflow and Codex-route tests remain included.

Run from the release root with its Python environment:

```sh
python -m pytest --import-mode=importlib \
  ops/native_fabric/unified_router/test_kimi_capacity.py \
  ops/native_fabric/unified_router/test_model_tiers.py \
  ops/native_fabric/unified_router/test_model_tiers_extended.py \
  ops/native_fabric/unified_router/test_overflow_glm.py \
  ops/native_fabric/unified_router/test_codex_route.py \
  ops/native_fabric/unified_router/test_mcpfix_wire.py -q
```

Provider congestion, external use of the same subscription and token-estimation error can still cause throttling. The router reacts to those signals; it cannot promise that an upstream provider never returns 429.
