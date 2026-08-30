# Grok Build G0 Native Substrate and Fast-Rollout Plan

**Operation:** `grok-build-g0-native-substrate-20260830-sol-001`  
**Workstream:** existing `WS:EXECUTIVE-CAPACITY-FABRIC`  
**Protected source / Skillpack pin:** `Mastermind@e19ef1c54cc6f2b7bfc652a78bf94a209fcb42b9`, `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Capability target:** `BUILT_NOT_PROVEN / PRODUCTION_INERT` at source merge; host proof is separate  
**Cognition route:** `CHAT_PRO_DEFAULT`

## Observable mission

Prove, without a model turn or Executive lifecycle effect, that one exact installed Grok Build CLI can be attested, can speak ACP v1 over stdio, exposes the provider-owned `cached_token` OAuth method, and can authenticate it headlessly; then use that evidence to unlock a separately bounded manual Grok Build canary while canonical automatic Executive routing continues through CF2 -> RF1 -> HF1.

## Why this matters

Mastermind already has substantial subscription-backed Grok capacity, but the canonical heterogeneous Executive worker path is still blocked behind Capacity Fabric and common-harness gates. Waiting for the entire automatic-routing stack before learning whether the official Grok Build execution surface is suitable would leave prepaid capacity idle and would couple provider discovery to the highest-collision control-plane paths.

G0 therefore creates **only the provider-native compatibility substrate** that HF1 can later consume. It does not create a Grok broker, provider router, lifecycle, queue, retry path, account store, credential bridge, capacity claim, or runtime alias.

## Current canonical state and dependency boundary

At the protected source pin:

- CF1 provider-capacity projection is complete.
- CF2-H0 native installed-host proof remains in progress.
- CF2-P0 and CF2-I remain downstream and unaccepted.
- RF1 remains gated on accepted CF2-I and owns provider-neutral suitability tiers.
- HF1 remains gated on accepted CF2-I and owns the provider-neutral WorkerExecutionAdapter/broker extraction.
- PF1 currently names Claude as the preferred first real non-Codex Executive worker after RF1/HF1.
- current common broker/router paths have active neighboring carriers and must not be touched by G0.
- Grok Secretary/OpenClaw (#188 family) is a separate Chairman/operator-surface program and is not a Grok Build worker carrier.

G0 changes none of those dependencies. A later source-law amendment may reorder the first real heterogeneous provider only after G0 host/canary evidence exists; this plan does not silently replace Claude PF1.

## Official provider contract used by G0

Current xAI Grok Build documentation exposes:

- provider-native browser/device OAuth login through `grok login` / `grok login --device-auth`;
- a headless CLI with explicit cwd/session/output/turn controls;
- ACP over JSON-RPC stdin/stdout through `grok agent stdio`;
- ACP initialization that advertises authentication methods, including `cached_token` when local OAuth exists;
- headless authentication of that cached credential before any `session/new` or `session/prompt` is required;
- `--no-auto-update` for stable automated/headless operation.

Provider documentation is capability evidence, not organizational authority. Runtime admission still belongs to Mastermind owners.

## Exact G0 source scope

New paths only:

1. `ops/executive_os/grok-build-preflight.py`
2. `tests/test_grok_build_preflight.py`
3. `docs/superpowers/plans/2026-08-30-grok-build-g0-native-substrate.md`

No existing `control_plane/**`, Model Router, Worker Broker, Worker adapter, Capacity, RuntimeBinding, Wake, Agent OS, Slack, Linear, provider configuration, credential, host installer, or production source changes.

## G0 contract

The preflight is provider-work-free in the model/inference sense. It may contact the provider during cached-OAuth authentication or refresh, but it must never create an ACP model session or submit a prompt.

Allowed provider commands are exactly:

```text
<absolute-grok-binary> --no-auto-update version
<absolute-grok-binary> --no-auto-update agent stdio
```

ACP messages emitted by G0 are exactly:

```text
initialize(protocolVersion=1, closed client metadata)
authenticate(methodId="cached_token", _meta.headless=true)
```

Forbidden G0 actions include `session/new`, `session/prompt`, resume/continue, worktree creation, model enumeration, login/logout, tool use, MCP, browser work, subagents, shell work, file editing, Git mutation, Executive Job creation or provider fallback.

## Secret/auth boundary

- Grok/xAI remains the OAuth credential owner.
- Mastermind never reads, copies, serializes, logs or transports cached token contents.
- The child process environment is allowlisted and explicitly excludes `XAI_API_KEY`; `GROK_HOME` may pass through so an already-approved provider home can be honored without exposing that path in the receipt.
- A successful G0 receipt proves only that ACP cached OAuth was usable for this preflight.
- It **does not prove** that every future model invocation is OAuth-only, because provider config/model credential precedence may differ from the G0 environment.
- Before a real Grok Executive worker is admitted, the actual execution realm must separately prove a provider-supported OAuth-only precedence/policy or fail closed. A managed `requirements.toml` policy may be used when supported by the enrolled xAI plan/estate; do not assume that enterprise control exists on every subscription.

## Public receipt

`mastermind.grok_build_preflight.v1` contains only:

```text
schema
observed_at
grok_binary_sha256
grok_version
acp_protocol_version
cached_token_offered
oauth_ready
model_turn_performed=false
executive_routing_ready=false
verdict
reason_codes
```

It contains no email, account identifier, token, home path, provider session id, host-private address, auth-file coordinate or raw provider output.

The positive verdict is intentionally:

```text
LOCAL_OAUTH_ACP_READY_NOT_ROUTABLE
```

It cannot be interpreted as Provider Capacity eligibility, Worker claim, Executive routing readiness or production proof.

## Data, time, null and correction behavior

- binary identity is SHA-256 of the exact regular executable bytes under a bounded maximum size;
- symlink, relative, missing, non-regular, non-executable or oversized binaries fail closed;
- `observed_at` is current UTC receipt time;
- ACP protocol version is fixed to v1 for this contract;
- missing `cached_token` is `CACHED_TOKEN_METHOD_UNAVAILABLE`, never inferred from other auth methods;
- ACP initialize error is `ACP_INITIALIZE_FAILED`; protocol-version mismatch is `ACP_PROTOCOL_UNSUPPORTED`; cached-token authenticate error is `ACP_AUTHENTICATION_FAILED`; none is mislabeled as a definite login problem;
- malformed/oversized/secret-shaped provider wire data fails closed and is never echoed;
- source or provider contract drift requires a new reviewed preflight version or source repair rather than permissive parsing.

## Deterministic versus provider behavior

Deterministic Mastermind code owns binary checks, hashing, environment construction, JSON-RPC request bytes, closed response validation, secret fences and receipt validation.

The provider owns OAuth state, token refresh, advertised ACP auth methods and authentication success. Provider output has **zero authority** over Executive lifecycle, routing, merge/release, Agent OS or company completion.

## Failure states

- `BINARY_UNAVAILABLE` / `BINARY_INVALID`
- `PROVIDER_TIMEOUT` / `PROVIDER_COMMAND_FAILED`
- `ACP_RESPONSE_INVALID` / `ACP_PROCESS_EXITED`
- `ACP_INITIALIZE_FAILED` / `ACP_PROTOCOL_UNSUPPORTED`
- `CACHED_TOKEN_METHOD_UNAVAILABLE`
- `ACP_AUTHENTICATION_FAILED`
- secret-shaped wire/refusal

Any provider-process ambiguity remains local G0 evidence only. Because G0 performs no model turn or company mutation, it never authorizes retry/failover of an Executive Attempt.

## Accelerated rollout sequence

### G0-A — source implementation

1. land the three-path provider-work-free preflight with RED->GREEN focused tests;
2. require hosted repository CI/security on the exact head;
3. independent review must confirm no model turn, no credential content access, no common-broker/router modification and no duplicate owner.

Completion: `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

### G0-B — intended-host read-only proof

On the intended Grok Build worker host:

1. resolve the exact installed Grok binary through the approved host/operator path;
2. run the exact accepted preflight once;
3. if cached OAuth is unavailable or authentication fails, stop and diagnose the provider-owned login state. When the cause is an absent/expired local login, a human/admin performs provider-native `grok login` or `grok login --device-auth` without exposing OAuth/browser/device secrets to the worker/model;
4. rerun the read-only preflight after the provider-native login/repair;
5. accept only `LOCAL_OAUTH_ACP_READY_NOT_ROUTABLE` with the exact binary/version digest and `model_turn_performed=false`.

No model canary is performed inside G0-B.

### G0-C — one manual/direct Grok Build work canary

After G0-B acceptance, create a **new child operation** for one low-risk bounded repository task whose result is independently verifiable. It is manual/session transport, not Executive dispatch.

Required controls:

- `PREFERRED_AVENUE: Grok`
- `RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE`
- isolated Git worktree and exact base SHA;
- explicit model/effort/turn limit;
- `--no-auto-update`;
- explicit allow/deny/sandbox/permission policy appropriate to the task;
- no hidden provider fallback;
- no API-key authentication unless a separately reviewed exception explicitly authorizes it;
- result goes through normal GitHub PR/CI and Sol review;
- no model result may self-authorize merge, release or next work.

This canary proves useful Grok Build labor can be consumed **before** automatic Executive placement is ready.

### G0-D — manual capacity exploitation

Once the canary is accepted, bounded implementation/research/review waves may preferentially route to the Grok avenue when it is the least-scarce capable route. This remains manual/direct assignment under current routing law; it is never mislabeled Executive automatic routing.

### Automatic-routing track — continue in parallel

```text
CF2-H0 native proof
-> CF2-P0
-> CF2-I
-> RF1 provider-neutral suitability
-> HF1 common WorkerExecutionAdapter/broker
-> reviewed real Grok adapter vertical
-> one real Executive Grok child Job canary
-> only then general Grok Executive routing
```

After G0 evidence, Sol should explicitly adjudicate whether the first real non-Codex PF vertical remains Claude-first, becomes Grok-first, or runs disjoint Claude/Grok canaries after HF1. Do not change PF1 source law implicitly.

## Acceptance tests

Focused source proof must include:

- absolute regular executable / symlink / missing / size checks;
- API-key and unrelated-secret environment suppression;
- exact `--no-auto-update version` and `--no-auto-update agent stdio` command allowlist;
- exact ACP initialize request and protocol v1 check;
- exact cached-token headless authenticate request;
- cached-token missing / protocol mismatch / malformed / duplicate auth-method refusal;
- authentication success plus typed initialize/protocol/authentication failure behavior;
- secret-shaped provider-wire rejection;
- receipt rejects any `model_turn_performed=true` or `executive_routing_ready=true` claim;
- static/procedural proof that G0 emits only `initialize` then `authenticate`, never session/prompt methods;
- opaque CLI failure output.

A host receipt is required before claiming local OAuth/ACP usable. A real bounded Grok coding result through GitHub/CI is required before claiming the Grok avenue operationally useful. Neither receipt proves automatic Executive routing.

## Stop condition

This source carrier stops after exact-head CI/security/review with the three-path G0 implementation. It does not execute host login, perform a model turn, modify Capacity/RF1/HF1/PF1, create a Grok Worker alias, install a service, or generalize routing.

## Continuation handoff

Return to Sol with:

- exact protected pickup and exact G0 head;
- exact three-file census;
- focused/hosted test + security receipts;
- independent review verdict;
- any official Grok CLI/ACP contract drift discovered;
- explicit confirmation of zero model prompt, zero Executive lifecycle effect and zero credential-content handling;
- the exact host action required next: G0-B preflight, or provider-native human login/repair only after the read-only result establishes cached OAuth is unavailable or cannot authenticate.
