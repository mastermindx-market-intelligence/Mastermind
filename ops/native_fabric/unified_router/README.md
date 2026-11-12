# Unified Capacity Fabric router

**Scope:** one loopback Anthropic-Messages edge over every fabric capacity
pool. T3 Code (or any Anthropic-wire client) selects a model slug — or a
`fabric/*` routing alias — and this router owns pool selection, cross-pool
load balancing and admission-time failover. It creates no new
credential store, queue or scheduler: incumbent gateways keep their pools and
quotas, incumbent config files keep their keys, and this router composes them.

## Source qualification and incumbent ownership

This retained edge candidate is not a global Model Router admission or a new
provider-quota owner. Its local `fabric/*` aliases are not measured C0-C3 task
qualifications. The accepted T3 default registration continues to exclude the
port8313 all-pools entry; integration must consume the existing Model Router,
Shared Provider Control and applicable Executive/native claim owners first.
Source release alone does not enroll accounts, authorize a workload, activate
this service, resolve a missing native selection, or prove installed consumers.
Existing installed entries and in-flight requests are not migrated by this code.

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
  choosing the lowest eligible per-model priority tier (`model_priority`
  overrides the route's `priority`). Within a tier, prefer the lowest
  `in_flight / effective_weight`; `model_weight` overrides the normal weight.
  Equally loaded routes on one provider use weighted rendezvous affinity on
  `metadata.user_id`. Across different providers they use weighted random
  selection, so one caller does not remain pinned to one plan. Affinity cannot
  override load or eligibility. Route weight zero drains every model; a model
  weight of zero can additionally drain only that model. A model override
  cannot undo a route-wide drain. Under load, pressure affects traffic shares;
  weights are not promises of fixed request percentages.
- **Aliases** (`fabric/frontier`, `fabric/balanced`, `fabric/fast`): ordered
  model cascades — the first model with an available route wins, so an
  exhausted pool transparently uses the next family.
- **Failover before a possible effect**: an unavailable local credential,
  OAuth owner preflight, or HTTPX connection/pool establishment failure may
  advance to another eligible route. The installed transport disables retries,
  redirects and environment proxies. Only its `ConnectError`, `ConnectTimeout`
  and `PoolTimeout` classifications establish that the HTTP request was never
  transmitted. Arbitrary injected transports cannot qualify a connection-phase
  retry from an exception name. Each route can be attempted once, within `FABRIC_MAX_ATTEMPTS`
  and one original total deadline. All HTTP responses (including 401, 429 and
  5xx), write/read ambiguity, cancellation and broken streams end the attempt
  without another provider/account/model inference call. No 401 refresh-and-
  resend occurs. Zero bytes received by the client does not prove zero upstream
  effect. Known-ineligible OAuth pools are excluded before selection.
- **Circuit recovery**: failures open a local circuit with capped exponential
  backoff and positive jitter. A valid provider `Retry-After` is a minimum,
  even when longer than the local cap. One half-open probe enters after the
  deadline. Generation fences stop older responses from changing newer health.
- Per-route `upstream_model` rewrite and case-insensitive public slugs keep
  vendor ids (`GLM-5.3-Flash`, dated ModelArk slugs) out of the public
  catalogue.
- `model_labels` preserves friendly catalogue names without changing model
  IDs. Per-model `model_params` supports a validated OpenAI `reasoning_effort`
  override after translation, keyed by the public slug. It cannot replace the
  request model, messages, tools, stream setting or authorization. Unknown or
  malformed overrides refuse startup.
- PAYG keys (e.g. the Z.AI `paas` pool) are deliberately not routed by
  default: subscription surfaces only, no silent spend.

## Endpoints

`POST /v1/messages`, `POST /v1/messages/count_tokens` (Anthropic wire,
streaming passthrough), `GET /v1/models` (unified catalogue + aliases),
`GET /healthz` (unauthenticated liveness), `GET /statusz` (bearer; per-route
health/counters, never keys).

## Bounded admission and completion

The service accepts through one listener and one Uvicorn worker. It deliberately
does not enable `SO_REUSEPORT`: overlapping independent processes would multiply
its process-local ceilings. An occupied listener fails closed, and the candidate
closes its socket on every normal or exceptional exit. The existing supervisor
must drain the incumbent before rebinding; this is not a zero-downtime claim.
The graceful request-drain budget is the configured total request deadline plus
the gateway's existing five-second cleanup bound, rounded up. Its default is
1805 seconds, not the former hard-coded 25 seconds. An external supervisor's
termination deadline must be qualified separately; changing this source does
not extend launchd's installed `ExitTimeOut` or authorize a service restart.

The service validates and freezes its settings before binding. Its process-wide bulkhead is
reserved before asynchronous credential reads; route and group reservations
are acquired without an intervening await. Do not multiply workers and assume
these local limits become global provider quotas.

| Setting | Default | Meaning |
|---|---:|---|
| `FABRIC_MAX_IN_FLIGHT` | 32 | Local process concurrency, including body uploads, admission and active streams |
| `FABRIC_MAX_ATTEMPTS` | 8 | At most 1–64 distinct route attempts, only while no upstream effect is possible |
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

The same selector that chooses the route produces a bounded explanation: disjoint
drain/circuit/probe/route/group exclusions, eligible count, chosen priority tier,
least-pressure candidate count and the actual affinity/random tie-break. Selection
and local permit acquisition share the hard exclusion predicate. The explanation
does not make another random choice or reserve capacity.

`selection.last` means the most recently evaluated model candidate, with a sequence
and monotonic age. It retains no requested model, alias, user/session identifier,
account, prompt or credential. Alias position/count is numeric. Owner-preflight
exclusions count routes matching that candidate and are separate from local health.
An empty post-preflight selector can report `FABRIC_MODEL_UNKNOWN` while the gateway
returns an owner refusal; `selector_reason` and `preflight_refusal` distinguish them.
`local_permit_acquired` proves only that local step. Owner eligibility is rechecked
before send, so this historical snapshot is never provider admission or send proof.
Fixed `selection.not_run` counters describe overload, invalid input or cancellation
before selection without attributing those requests to an older route decision.
Reading status serializes existing observations and performs no selection or owner
read. Route and reason metric keys are bounded by the configuration and fixed enums.

Attempt/failover/exhaustion counters describe the bounded pre-send ladder.
`upstream_send_calls_total` counts transport invocations, including connection
failures that transmitted no request. Per-route `attempt_failed` is separate
from final client outcomes: a successful fallback is one served request, not a
failed request plus a success. Local pool saturation, credentials and owner holds
do not open provider-health circuits. A fallback releases only its old route,
group and probe reservation; the global reservation, request ID and absolute
deadline remain owned until the terminal result and shielded cleanup.

Fixed latency bins supplement the EWMA. They use noncumulative counts with inclusive
upper bounds and a final overflow bin (`null` upper bound). Their population is
successful completions only, and their clock begins at local admission reservation,
including body upload and credential preflight. Missing first-content observations
stay missing. These are not pure provider TTFT or all-attempt latency measurements;
failed/cancelled requests remain visible in their separate outcome counters.

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

### Graceful release boundary

The observed incumbent M2 job uses one Uvicorn worker, `KeepAlive.SuccessfulExit=false`
and a loaded launchd stop timeout of five seconds. Its old application has neither
a drain endpoint nor a total request deadline. Uvicorn's first SIGTERM closes new
connections and waits for active responses; a launchd stop can impose its separate
short kill deadline. `kickstart -k`, SIGHUP and an observed quiet interval do not
establish a request-preserving upgrade.

The initial cutover therefore requires the incumbent consumer/admission owner to
hold new submissions, then one direct SIGTERM to the identity-checked original
worker and observation of its actual completion. Keep the hold while reconciling
any KeepAlive replacement, unloading the old definition, and selecting the exact
protected-accepted immutable generation. A stuck old request needs its original
owner's reconciliation; never force it away and replay it. Stage and verify the
old generation/definition for rollback, then verify new identity, status, catalogue
and real Hermes/DSH/T3 turns before reopening traffic. Rollback restores code and
the recorded service definition, not old shared-auth or quota snapshots.

This is a conditional operating procedure, not a performed deployment or evidence
that an effective ingress hold exists. The acceptance record retains those gates.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r ops/native_fabric/unified_router/requirements.txt
FABRIC_ROUTER_TOKEN=… FABRIC_ROUTES_JSON=./routes.json .venv/bin/python -m ops.native_fabric.unified_router.service --env-file router.env --port 8313
```

A launchd unit (`ai.mastermind.fabric-router`) runs it on `127.0.0.1:8313`;
`integrations/t3_capacity_fabric` registers it in T3 as the provider
**Capacity Fabric** with the full catalogue.
