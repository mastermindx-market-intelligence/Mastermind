# Unified Capacity Fabric router

**Scope:** one loopback Anthropic-Messages edge over every fabric capacity
pool. T3 Code (or any Anthropic-wire client) selects a model slug — or a
`fabric/*` routing alias — and this router owns pool selection, cross-pool
load balancing, key rotation and admission-time failover. It creates no new
credential store, queue or scheduler: incumbent gateways keep their pools and
quotas, incumbent config files keep their keys, and this router composes them.

## Route kinds

| kind | authorization | example pools |
|---|---|---|
| `gateway` | loopback `FABRIC_PROXY_TOKEN` of an incumbent fabric gateway | `anthropic_oauth` (8312, Claude Max pool), `experiential` (8311, multi-vendor Max plan) |
| `config_file` | pointer into an incumbent pool config | GLM coding plan (`~/.glm/config.json`), Bailian token plan (`~/.bailian/config.json`, 3 keys = 3 routes), MiniMax token plan (`~/.minimax/config.json`) |
| `credential_pool` | Hermes `credential_pool` label or `env:` source | BytePlus coding plan key |

Vendor endpoints are the org's existing **Anthropic-wire** subscription
surfaces (`api.z.ai/api/anthropic`, `…aliyuncs.com/apps/anthropic`,
`api.minimax.io/anthropic`, `ark…bytepluses.com/api/coding`); pools that only
speak the OpenAI wire are served through the closed translator in `wire.py`
(request/response + SSE, tool-use round trips).

## Routing rules

- **Exact slug**: all routes serving the model, ordered by `priority` tier;
  within a tier, weighted random selection with **caller affinity** on
  `metadata.user_id` so prompt-cache locality survives across requests.
- **Aliases** (`fabric/frontier`, `fabric/balanced`, `fabric/fast`): ordered
  model cascades — the first model with an available route wins, so an
  exhausted pool transparently uses the next family.
- **Admission-time failover only**: a 429/5xx benches that route locally
  (30s x consecutive failures, capped) and the *next* request picks another
  route. A request is never replayed after a possible upstream effect.
- Per-route `upstream_model` rewrite and case-insensitive public slugs keep
  vendor ids (`GLM-5.3-Flash`, dated ModelArk slugs) out of the public
  catalogue.
- PAYG keys (e.g. the Z.AI `paas` pool) are deliberately not routed by
  default: subscription surfaces only, no silent spend.

## Endpoints

`POST /v1/messages`, `POST /v1/messages/count_tokens` (Anthropic wire,
streaming passthrough), `GET /v1/models` (unified catalogue + aliases),
`GET /healthz` (unauthenticated liveness), `GET /statusz` (bearer; per-route
health/counters, never keys).

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r ops/native_fabric/unified_router/requirements.txt
FABRIC_ROUTER_TOKEN=… FABRIC_ROUTES_JSON=./routes.json .venv/bin/python -m ops.native_fabric.unified_router.service --env-file router.env --port 8313
```

A launchd unit (`ai.mastermind.fabric-router`) runs it on `127.0.0.1:8313`;
`integrations/t3_capacity_fabric` registers it in T3 as the provider
**Capacity Fabric** with the full catalogue.
