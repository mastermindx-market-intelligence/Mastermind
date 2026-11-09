# Unified Capacity Fabric router

**Scope:** one loopback Anthropic-Messages edge over every fabric capacity
pool. T3 Code (or any Anthropic-wire client) selects a model slug — or a
`fabric/*` routing alias — and this router owns pool selection, cross-pool
load balancing and admission-time failover. It creates no new
credential store, queue or scheduler: incumbent gateways keep their pools and
quotas, incumbent config files keep their keys, and this router composes them.

## Route kinds

| kind | authorization | example pools |
|---|---|---|
| `gateway` | loopback `FABRIC_PROXY_TOKEN` of an incumbent fabric gateway | `anthropic_oauth` (8312, Claude Max pool), `experiential` (8311, multi-vendor Max plan) |
| `config_file` | pointer into an incumbent pool config | GLM coding plan (`~/.glm/config.json`), Bailian token plan (`~/.bailian/config.json`, 3 keys = 3 routes), MiniMax token plan (`~/.minimax/config.json`) |
| `credential_pool` | Hermes `credential_pool` label or `env:` source | BytePlus coding plan key |
| `oauth_pool` | eligible OAuth access token read from the incumbent Hermes pool; Responses wire | ChatGPT Codex pool |

Vendor endpoints are the org's existing **Anthropic-wire** subscription
surfaces (`api.z.ai/api/anthropic`, `…aliyuncs.com/apps/anthropic`,
`api.minimax.io/anthropic`, `ark…bytepluses.com/api/coding`); pools that only
speak the OpenAI wire are served through the closed translator in `wire.py`
(request/response + SSE, tool-use round trips).

## Routing rules

- **Exact slug**: filter disabled, unavailable and saturated routes before
  choosing the lowest eligible `priority` tier. Within a tier, prefer the
  lowest `in_flight / weight`. Equal-load routes use weighted rendezvous
  affinity on `metadata.user_id`, or weighted random selection without a key.
  Affinity is soft and cannot override load or eligibility. Weight zero drains
  a route; removing one member does not remap callers assigned to other members.
- **Aliases** (`fabric/frontier`, `fabric/balanced`, `fabric/fast`): ordered
  model cascades — the first model with an available route wins, so an
  exhausted pool transparently uses the next family.
- **Admission-time failover only**: one inference send per incoming request.
  No 401 refresh-and-resend, redirect, transport retry or 5xx account rotation.
  A later independent request may use another eligible route. Known-ineligible
  OAuth pools are excluded before selection, allowing an eligible fallback.
- **Circuit recovery**: failures open a local circuit with capped exponential
  backoff and positive jitter. A valid provider `Retry-After` is a minimum,
  even when longer than the local cap. One half-open probe enters after the
  deadline. Generation fences stop older responses from changing newer health.
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

## Bounded admission and completion

The installed service runs one Uvicorn worker. Its process-wide bulkhead is
reserved before asynchronous credential reads; route and group reservations
are acquired without an intervening await. Do not multiply workers and assume
these local limits become global provider quotas.

| Setting | Default | Meaning |
|---|---:|---|
| `FABRIC_MAX_IN_FLIGHT` | 32 | Local process concurrency, including body uploads, admission and active streams |
| Route `max_in_flight` | 0 | Optional per-route ceiling; zero means only other ceilings apply |
| Route `concurrency_group` and `group_max_in_flight` | unset | Explicit shared local ceiling across routes; every group member must agree |
| `FABRIC_REQUEST_TIMEOUT_S` | 1800 | Total admitted-request deadline, including streaming keepalives |
| `FABRIC_REQUEST_BODY_TIMEOUT_S` | 30 | Incoming body upload deadline inside the process concurrency limit |
| `FABRIC_UPSTREAM_TIMEOUT_S` | 900 | Upstream HTTP inactivity timeout |
| `FABRIC_MAX_BODY_BYTES` | 8388608 | Incoming request body limit |
| `FABRIC_MAX_RESPONSE_BYTES` | 16777216 | Upstream response limit, including streamed bytes |
| `FABRIC_MAX_SSE_EVENT_BYTES` | 1048576 | Bound for an unfinished SSE frame |

Ceilings are local protection, not discovered subscription capacity. Existing
pool owners retain five-hour/weekly/monthly allowances, shared-account identity,
authorization, budget and queue fairness. A group is configured only from an
explicit known relationship; model names and aliases do not prove shared quota.
Configuration is loaded at service start; this change adds no live reload owner.

HTTP headers alone do not count as success. Anthropic streams require a terminal
message event; OpenAI streams require an explicit finish reason and `[DONE]`;
Responses streams require a completed response or the supported explicit
`max_output_tokens` incomplete condition. Provider error events, truncated EOF,
malformed non-stream bodies, response limits and deadline expiry fail visibly.
Cancellation closes upstream resources and releases reservations, including a
disconnect before the stream generator starts. Cleanup is bounded and shielded.

## OAuth owner boundary

The request path reads the current Hermes account rows and respects owner `dead`
states, observed exhaustion, unknown reset times and known token expiry. It
never calls the OAuth token endpoint. When a token is known to expire within
30 seconds, another eligible account may be selected before inference. If no
such account exists, `FABRIC_OAUTH_OWNER_REFRESH_REQUIRED` tells the caller that
the incumbent auth owner must rotate it. A later request adopts the owner's
new token directly from the same store. This refusal does not open a circuit
or fabricate a quota reset time.

An inference 429 benches exactly its account using the incumbent lock and status
fields. The write is atomic, stamps `last_status_at` for the owner's stale-write
merge, never shortens an existing hold and cannot replace a stronger `dead`
state. It stores constant reasons, never provider response text. A read-only
status call neither refreshes credentials nor sends provider probes.

The retained explicit `refresh_account` compatibility helper is not called by
the gateway. An external owner using it remains responsible for reconciling an
uncertain remote grant consumption before another attempt. File locking and
atomic replacement do not establish exactly-once OAuth effects across a crash.
No new uncertainty ledger or overloaded `dead` state is introduced here.

## Operational evidence

`/statusz` reports local in-flight counts, configured ceilings, circuit state,
cooldown remaining on the correct monotonic clock, selected/served/refused/
failed/cancelled counts, admission refusals, cleanup failures and successful
header/first-content/completion latency EWMAs. These measurements are not
provider quota estimates. Latency is observed; automatic learned weights and
quality/model substitutions remain off pending representative evaluation.

Successful routed responses carry `x-fabric-route`, `x-fabric-model`,
`x-fabric-request-id` and `x-fabric-policy`. They expose neither account identity,
credentials nor prompts. Counters and local circuit history are process-local
and reset at restart; they are not a durable usage or billing ledger.

Offline regression qualification (mock providers and temporary auth fixtures):

```bash
python -m pytest -q tests/test_unified_fabric_router.py tests/test_unified_router_resilience.py ops/native_fabric/unified_router/test_codex_route.py
```

Release and installed acceptance are tracked in
`docs/CAPACITY_ROUTER_RESILIENCE.md`. A passing suite is not evidence that an
unmerged candidate has been installed or that a consumer completed a real turn.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r ops/native_fabric/unified_router/requirements.txt
FABRIC_ROUTER_TOKEN=… FABRIC_ROUTES_JSON=./routes.json .venv/bin/python -m ops.native_fabric.unified_router.service --env-file router.env --port 8313
```

A launchd unit (`ai.mastermind.fabric-router`) runs it on `127.0.0.1:8313`;
`integrations/t3_capacity_fabric` registers it in T3 as the provider
**Capacity Fabric** with the full catalogue.
