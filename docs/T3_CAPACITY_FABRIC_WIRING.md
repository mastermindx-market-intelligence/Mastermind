# T3 Code — Capacity Fabric wiring

Parent: [#983](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983).
Carrier: the Capacity Fabric OS integration branch (this PR). Runtime acceptance
for the `t3_code` consumer remains under #983; this document records the source
wiring, the installed registration and its exact boundaries.

## Outcome

T3 Code can now select fabric capacity natively: the fabric's local serving
gateways appear as first-class T3 providers (`claudeAgent` driver instances
`fabric_claude` and `fabric_experiential`), each exposing the gateway's live
authenticated catalogue as T3-custom models. **The fabric owns every routing,
admission, pool-rotation and load-balancing decision**; T3 only chooses a model
slug. No T3-side fallback, retry ladder or second provider is configured: a
fabric refusal (budget window, cooldown, queue deadline, plan policy) surfaces
to the thread unchanged.

## The unified router (all pools, all keys, smart routing)

`ops/native_fabric/unified_router` (launchd `ai.mastermind.fabric-router`,
`127.0.0.1:8313`) is the fabric's single intelligent edge. T3's provider
**Capacity Fabric** (`capacity_fabric`) points at it and exposes the union
catalogue of configured models and `fabric/frontier|balanced|fast` aliases.

- **Every pool, every key, no new custody**: routes compose the incumbent
  owners — the two local gateways (their own loopback tokens), the GLM coding
  plan (`~/.glm/config.json`), the Bailian token plan (3-key rotation,
  `~/.bailian/config.json`), the MiniMax token plan (`~/.minimax/config.json`)
  and the BytePlus coding plan key — each read live at request time through
  the same pointers the incumbents use. PAYG keys (Z.AI `paas`) are
  deliberately not routed: subscription surfaces only, no silent spend.
- **Smart routing**: exact slugs resolve to all serving routes in priority
  tiers; within a tier, weighted selection with caller affinity
  (`metadata.user_id`) preserves prompt-cache locality where the tier is a
  single upstream provider; across providers the configured weights
  distribute the traffic instead (a lone caller must not monopolise one
  plan). Routes also accept per-model `model_priority`/`model_weight`
  overrides, so one slug can join several providers in a single tier
  without disturbing the route's other models — deployed for
  `deepseek-v4.1-flash` (Chairman wide-distribution ruling, 2026-11-09:
  labs_pool / opencode $40 / BytePlus weight 2, opencode $10 weight 1, one
  tier). `fabric/*` aliases are
  ordered family cascades, so an exhausted pool transparently uses the next
  family. 429/5xx benches a route locally with capped exponential backoff and the
  next request fails over — admission-time only, never a replay after a
  possible effect.
- **Bounded pre-send failover** (2026-11-09): local credential or owner
  preflight refusal, or a connection/pool failure proven by the service-owned
  direct HTTPX transport to precede transmission, can advance to another
  eligible route. Selection rechecks priority, per-model weights, current
  in-flight pressure and the alias cascade after each such failure. The
  entire request retains one deadline and global reservation, with at most
  `FABRIC_MAX_ATTEMPTS` (default 8, maximum 64) distinct route attempts.
  **Every HTTP response is terminal for that request**, including 401/403,
  404, 429 and 5xx. No client-visible bytes is not evidence of no upstream
  effect. Read/write ambiguity, stream truncation and post-send cancellation
  never replay on another route, account or model. Injected transports do
  not establish a safe connection phase from an exception class alone.
  `count_tokens` keeps only Anthropic-wire routes; its 404 does not bench
  generation. Exhausted pre-send admission returns a typed 503.
  `statusz` exposes attempts, failovers, exhaustion and per-route failed
  attempts, alongside final request outcomes and success-only latency.
- **Unorouter fallback tier** (Chairman integration, 2026-11-09):
  `unorouter_free` (priority 40) and `unorouter_paid` (priority 45) compose
  the Unorouter OpenAI-wire catalogue as capacity fallback rungs for shared
  slugs — `glm-5.3`/`glm-5.3-flash` map to `:free` upstream ids,
  `deepseek-v4.1-flash` to `deepseek-v4.1-flash-1017:free` (free rung) and
  `deepseek-v4.1-flash-1017` (paid rung, same public slug), `gpt-5.6-sol`
  same id — plus three new Free-labelled slugs (`qwen3.8-27b:free`,
  `hy3:free`, `qwen3-coder-plus:free`; `model_labels` drives `/v1/models`
  display names). The free pools are low-success-rate by design and sit
  strictly below the primaries: they serve only when the primary tiers are
  cooling or exhausted. `minimax-m3.1-flash:free` is deliberately excluded
  (the upstream hangs, which would stall a rung until the read timeout);
  `qwen3.8-27b:free` needs `reasoning_effort: medium` via the per-model
  `model_params` override (applied after OpenAI-wire translation). The
  deployed model-exclusivity guard allows the GLM fallback lane on
  `unorouter_free` only; primary GLM serving stays Z.ai-only.
- **Wire coverage**: all default pools speak Anthropic wire natively
  (passthrough, streaming untouched); OpenAI-wire pools route through the
  closed translator (`wire.py`: tools, SSE events, usage round trips).
- **Truthful capacity**: the Bailian monthly exhaustion surfaced above is a
  real vendor quota state passed through verbatim — the router never invents
  headroom.

`GET /statusz` reports per-route health/counters (never keys); `GET /v1/models`
is the unified catalogue. Remaining un-routed capacity: Codex ChatGPT seats
(backend protocol owned by the codex CLI lane), xAI OAuth (token-refresh lane),
OpenCode-Go free tier and the Cursor pool — each drops in as one more route
entry plus key pointer.

## Architecture

```
T3 Code (claudeAgent driver, Claude Code CLI)
  └─ ANTHROPIC_BASE_URL → http://127.0.0.1:8312   fabric: anthropic_oauth_proxy
       │  Anthropic Messages wire, bearer = FABRIC_PROXY_TOKEN
       ├─ admission: rolling 5h + weekly weighted budgets per account
       ├─ pool rotation: round-robin max-* OAuth accounts, cooldowns, in-flight caps
       └─ model weights (fable 2.0 / opus 1.5 / rest 1.0) — capacity-aware LB
  └─ ANTHROPIC_BASE_URL → http://127.0.0.1:8311   fabric: experiential_proxy
       │  Anthropic Messages wire (new `/v1/messages` + `/v1/messages/count_tokens`)
       ├─ admission: durable sliding-window RPM per key + optional org ceiling
       ├─ key rotation: round-robin over operator-configured keys
       └─ funding boundary: operator-deployed EXPLABS_ANTHROPIC_MODELS catalogue
```

Registration is performed by `integrations/t3_capacity_fabric` (pure stdlib):

- `endpoints.py` — the installed fabric serving endpoints and their env-file
  token locations; catalogues are read from each gateway's authenticated
  `GET /v1/models`. Nothing is invented locally.
- `t3_config.py` — idempotent, backup-first writes into T3's live-watched
  `~/.t3/userdata/settings.json` (tightened to 0600 because it carries gateway
  tokens). The T3 UI's Keychain secret store is never hand-authored.
- `registration.py` / `__main__.py` — `status | plan | apply | verify`; every
  apply backs up `settings.json` before an atomic replace and refuses to
  register an unhealthy gateway.

## Experiential edge: Anthropic Messages surface

`ops/native_fabric/experiential_proxy/gateway.py` previously spoke only the
OpenAI wire. It now also accepts `POST /v1/messages` and
`POST /v1/messages/count_tokens` through the **same** durable RPM admission,
key rotation, bounded queue and streaming passthrough as the existing
endpoints. The funding boundary for this surface is the operator-deployed
`EXPLABS_ANTHROPIC_MODELS` catalogue (`control_plane/experiential_plan_policy.py`):

- unset/empty → every Anthropic request is refused `PLAN_ANTHROPIC_NOT_ENABLED`
  **before** RPM/slot reservation (zero spend, zero queue use);
- the request `model` must be an exact member of the deployed list
  (`PLAN_MODEL_NOT_ADMITTED` otherwise);
- routing-override body fields are refused; JSON is parsed as a closed object;
- an optional `x-fabric-plan-policy: <anthropic_policy_digest(models)>` header
  binds a caller to the exact deployed catalogue (409 on mismatch);
- no model rewrite, no idempotency forwarding, no replay: single attempt.

`GET /statusz` discloses `anthropic_surface` and its digest, never the slugs or
keys.

## Installed registration (this host, 2026-11-09)

- `ai.mastermind.anthropic-gateway` (8312): registered as T3 provider
  `fabric_claude` — 12-model Claude catalogue over the pooled `max-*` accounts.
- `ai.mastermind.experiential-gateway` (8311): deployed a new release
  generation extending the gateway with the Anthropic surface;
  `EXPLABS_ANTHROPIC_MODELS` set to the vendor's Anthropic-wire catalogue
  (16 multi-vendor slugs: Claude/GPT/GLM/DeepSeek/Qwen/Kimi/Grok/Gemini/MiniMax);
  registered as T3 provider `fabric_experiential`.
- Both gateway env files and `settings.json` were backed up before any change;
  receipts are in the delivery thread, not in this repository.

The pre-existing T3 `experiential` provider (direct to
`https://api.experientiallabs.ai`) is left untouched: retiring it in favour of
the fabric edge is an operator decision, not this wiring's to take.

## Boundaries and remaining work

- Pools not yet served by a local fabric gateway (GLM canonical paid lease
  gateway, grok47 quota pools, native application pools behind the lease
  broker) register through the same `FabricEndpoint` seam once their serving
  surface is installed; the registration tooling does not create gateways.
- The fabric view panel from this PR keeps `admission_authorized=false`: it is
  a monitor. Actual admission is the gateways' budget/RPM/lease logic above.
- Consumer acceptance for `t3_code` (thread launch behaviour, occupancy,
  result consumption under load) stays with #983's acceptance matrix.
