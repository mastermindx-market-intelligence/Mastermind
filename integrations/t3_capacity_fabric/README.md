# T3 Code — Capacity Fabric provider registration

This package registers the fabric's local serving gateways as native T3 Code
model providers. T3 keeps providers in `~/.t3/userdata/settings.json`
(`providerInstances`), live-watched by the app: registration applies without
a T3 restart.

## Boundary

- The **fabric owns routing, admission, pool rotation and load balancing**.
  Each registered provider is one `claudeAgent` instance whose
  `ANTHROPIC_BASE_URL` points at a loopback fabric gateway. T3 only picks a
  model slug from the gateway's authenticated catalogue (`GET /v1/models`).
- **No T3-side fallback is configured**: a fabric refusal (cooldown, budget,
  queue, plan policy) surfaces to the thread as-is. There is no second
  provider, retry ladder or credential store here.
- The gateway proxy token stays on this host: it is read from the gateway's
  own 600-mode env file and stored as a `sensitive` environment value inside
  T3's 0600 `settings.json` (the T3 UI may later migrate it to its Keychain
  secret store; both forms keep working).

## Endpoints

| endpoint | gateway | pool | catalogue |
|---|---|---|---|
| `unified_router` | `http://127.0.0.1:8313` (`ai.mastermind.fabric-router`) | **all pools** behind one intelligent edge: Claude Max, Experiential Max, GLM coding plan, Bailian token plan (3 keys), MiniMax token plan, BytePlus coding plan | 32 models + `fabric/frontier\|balanced\|fast` routing aliases |
| `anthropic_oauth` | `http://127.0.0.1:8312` (`ai.mastermind.anthropic-gateway`) | Claude Max OAuth accounts (`max-*`) with rolling 5h/weekly budgets, cooldowns, model weights, round-robin | 12 Claude ids incl. `claude-opus-5-5`, `claude-fable-5.1` |
| `experiential` | `http://127.0.0.1:8311` (`ai.mastermind.experiential-gateway`) | Experiential Labs keys behind durable sliding-window RPM admission; Anthropic Messages surface (`/v1/messages`) admitted by the operator-deployed `EXPLABS_ANTHROPIC_MODELS` catalogue | operator-configured multi-vendor slugs |

Additional fabric pools (GLM canonical paid lease gateway, grok47, native
application pools) register through the same seam once their serving gateway
is installed: add a `FabricEndpoint` and re-run `apply`.

## Usage

```bash
python -m integrations.t3_capacity_fabric status   # health + registration state
python -m integrations.t3_capacity_fabric plan     # exact diff, writes nothing
python -m integrations.t3_capacity_fabric apply    # backup + register + secret
python -m integrations.t3_capacity_fabric verify   # health + catalogue + drift
```

`apply` writes a timestamped backup of `settings.json` next to T3's userdata
(`capacity-fabric-backups/`) before the atomic replace, and creates each
provider's `homePath` (`~/.t3/providers/fabric-<endpoint>`, 0700) so provider
state never shares the interactive Claude Code home.

T3 picks up new provider instances on its next start; already-open sessions
keep their model selection.

## Fabric edge consumer contract (T3, Hermes, any sibling consumer)

One boundary, three loopback edges — consumers carry **only the local gateway
token**, never vendor keys; the fabric owns admission, key/account rotation
and load balancing; there is no consumer-side fallback.

| edge | wire | auth | admission boundary |
|---|---|---|---|
| `127.0.0.1:8312` (anthropic gateway) | Anthropic Messages | `Bearer` gateway token from `anthropic-gateway/gateway.env` | pooled Claude Max OAuth accounts: rolling 5h/weekly budgets, cooldowns, model weights |
| `127.0.0.1:8311` (experiential edge) | **both**: Anthropic Messages (`/v1/messages`, `/v1/messages/count_tokens`) **and** OpenAI (`/v1/chat/completions`, `/v1/responses`, …) | `Bearer` gateway token from `experiential-gateway/gateway.env` | per-key durable sliding-window RPM + org ceiling; Anthropic surface admits exactly `EXPLABS_ANTHROPIC_MODELS`; OpenAI surface enforces `EXPLABS_PLAN_POLICY` |
| `127.0.0.1:8313` (unified router) | Anthropic Messages | `Bearer` router token from `fabric-router/router.env` | every pool above plus GLM coding plan (3-account rotation), Bailian token plan (3 keys), MiniMax, BytePlus; `fabric/*` aliases; admission-time failover only |

OpenAI-wire POSTs on 8311 **must** bind to the deployed policy with
`x-fabric-plan-policy: <plan_policy_digest(EXPLABS_PLAN_POLICY)>` (409
otherwise); the current `free_and_uncensored` digest is published by
`GET /statusz`. Anthropic-wire POSTs may bind optionally to the Anthropic
catalogue digest (`anthropic_policy_digest` in `/statusz`). A request is never
replayed across keys/routes after a possible effect; refusals are typed
(`PLAN_*`, `FABRIC_*`).
