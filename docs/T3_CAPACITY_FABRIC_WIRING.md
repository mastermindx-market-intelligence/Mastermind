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
