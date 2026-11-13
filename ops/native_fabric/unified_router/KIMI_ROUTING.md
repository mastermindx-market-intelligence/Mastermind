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

## Follow-on resilience upgrade

The decision path remains eligibility, independent capacity reservation, weighted selection and session affinity, durable admission, one upstream inference, then validated settlement. Provider-side MCP configuration and state require a compatible native wire. Completed MCP histories can cross wires without losing their function names, call IDs, results or order; server provenance is not a substitute function name.

OAuth admission reads the incumbent owner store off the event loop, excludes owner-held, known-expired and exhausted accounts, and selects an eligible identity before sending. A locally excluded pool may use an eligible alternative without damaging provider health. Once sent, a 401, 403, 429 or server failure never rotates identities, refreshes a token or replays that inference. Token refresh remains the incumbent owner's responsibility. Rate-limit writes use the existing owner lock and atomic private replacement, preserve stronger holds and longer reset deadlines, and retain unknown exhaustion when no valid reset is supplied. Retained asynchronous writers finish through client cancellation; cumulative observations and revision-guarded completion prevent overlapping writes from clearing newer holds.

Responses streams require a validated completion event, or an explicit maximum-output-token terminal. EOF, malformed events, failed responses, unknown incomplete reasons and conflicting tool identities cannot count as successful work. Valid completion does not require an optional `[DONE]` marker. Translated messages have unique local IDs. Both Responses and Chat translation report final observed input, cache-read and output usage; uncached input plus cache-read equals total input. Chat streams continue through a trailing usage-only chunk before `[DONE]`, keeping that observation inside the admission lifetime. Missing provider usage remains conservatively reserved in the admission ledger.

Malformed or non-object tool arguments return a typed translation failure; they are never wrapped as invented executable arguments or printed into logs. Provider refusal logs and client errors contain bounded router reason codes, not raw provider bodies.

The second activation retains the proven subscription policy and ledger. It uses exact phase-one source/config preimages, the same launchd slot and reload lock, waits for the incumbent process to drain and exit, and verifies ledger restoration and measured source generation before consumer proof. The source archive remains a draft reconciliation PR until broader protected-master route/group contracts are qualified; direct M2 activation does not waive repository protections.

## Concurrent dispatch and circuit recovery

The same active-admission ledger now composes the global ceiling of 128, per-resource limits, optional route `max_in_flight`, and optional `concurrency_group`/`group_max_in_flight`. Group occupancy does not merge token windows or provider balance observations. The 37 current route declarations omit the optional fields, so their default zero/empty values preserve existing resource policy. Invalid or contradictory group limits refuse configuration. Limit changes affect future admissions; active group or resource reassignment still requires drain.

Every inference captures its route's circuit generation. Old successes and generic failures cannot change a newer circuit decision, while authoritative quota and permission refusals remain effective. Cooldown deadlines cannot shorten. After the cooldown, one current inference probe may run; its validated success closes the circuit. The existing admission checkpoint preserves the need for a probe across restart.

Token counting uses operation-tagged entries in the same active ledger. It consumes dispatch concurrency without reserving inference tokens, changes no inference health/cache/overflow state, and releases exactly once on completion or cancellation. Count-only entries are excluded from uncertain-inference recovery holds. `/routingz` exposes separate inference/metering activity, metering counters and group occupancy; `/statusz` includes route caps and circuit generation/probe state.

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
  ops/native_fabric/unified_router/test_mcpfix_wire.py \
  ops/native_fabric/unified_router/test_router_resilience_upgrade.py \
  ops/native_fabric/unified_router/test_router_concurrency_upgrade.py -q
```

Provider congestion, external use of the same subscription and token-estimation error can still cause throttling. The router reacts to those signals; it cannot promise that an upstream provider never returns 429.
