# Grok Build G0 Native Substrate and Fast-Rollout Plan

**Operation:** `grok-build-g0-native-substrate-20260830-sol-001`  
**Workstream:** existing `WS:EXECUTIVE-CAPACITY-FABRIC`  
**Protected source / Skillpack pin:** `Mastermind@e19ef1c54cc6f2b7bfc652a78bf94a209fcb42b9`, `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Capability target:** `BUILT_NOT_PROVEN / PRODUCTION_INERT` at source merge; host proof is separate  
**Cognition route:** `CHAT_PRO_DEFAULT`

## Observable mission

Prove, without a model turn or Executive lifecycle effect, that one exact installed Grok Build executable can be attested by stable binary identity, can speak ACP v1 over stdio, exposes the provider-owned `cached_token` OAuth method, and can authenticate it headlessly. Use that evidence to unlock a separately bounded manual Grok Build canary while canonical automatic Executive routing continues through CF2 -> RF1 -> HF1.

## Why this matters

Mastermind has substantial subscription-backed Grok capacity, while canonical heterogeneous Executive placement still has Capacity Fabric and common-harness gates ahead of it. Waiting for the entire automatic-routing stack before learning or using the official Grok Build seam would strand prepaid capacity and would couple provider discovery to high-collision control-plane paths.

G0 therefore creates **only the provider-native compatibility substrate** that HF1 can later consume. It does not create a Grok broker, provider router, lifecycle, queue, retry path, account store, credential bridge, capacity claim, or runtime alias.

## Current canonical dependency boundary

At the protected source pin:

- CF1 provider-capacity projection is complete.
- CF2-H0 native installed-host proof remains in progress.
- CF2-P0 and CF2-I remain downstream and unaccepted.
- RF1 remains gated on accepted CF2-I and owns provider-neutral suitability tiers.
- HF1 remains gated on accepted CF2-I and owns the provider-neutral WorkerExecutionAdapter/broker extraction.
- PF1 currently names Claude as the preferred first real non-Codex Executive worker after RF1/HF1.
- common broker/router paths have neighboring active carriers and are outside G0.
- Grok Secretary/OpenClaw (#188 family) is a separate Chairman/operator-surface program and is not a Grok Build worker carrier.

G0 changes none of those dependencies. A later source-law amendment may reorder the first real heterogeneous provider only after real G0 host/canary evidence exists; this carrier does not silently replace Claude PF1.

## Official provider contract used by G0

Current xAI Grok Build documentation exposes:

- browser/device OAuth through `grok login` / `grok login --device-auth`;
- headless CLI controls;
- ACP over newline-delimited JSON-RPC stdin/stdout through `grok agent stdio`;
- ACP v1 initialization with advertised authentication methods;
- explicit `cached_token` headless authentication before any model session is required;
- `--no-auto-update` for stable automated/headless operation.

Provider documentation is capability evidence, not organizational authority. Runtime admission remains with Mastermind owners.

## Exact G0 source scope

New paths only:

1. `ops/executive_os/grok-build-preflight.py`
2. `tests/test_grok_build_preflight.py`
3. `docs/superpowers/plans/2026-08-30-grok-build-g0-native-substrate.md`

No existing `control_plane/**`, Model Router, Worker Broker, Worker adapter, Capacity, RuntimeBinding, Wake, Agent OS, Slack, Linear, provider configuration, credential, host installer, or production service changes.

## G0 command and ACP contract

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

Forbidden G0 actions include `session/new`, `session/prompt`, resume/continue, worktree creation, model enumeration, login/logout, tool use, MCP, browser work, subagents, shell work, file editing, Git mutation, Executive Job creation, capacity claim, or provider fallback.

## Stable executable identity / TOCTOU law

Before provider interaction G0 snapshots the exact absolute regular executable:

```text
sha256
size
device
inode
mtime_ns
```

`--no-auto-update` disables the normal self-update path. G0 then rechecks the complete identity plus a fresh SHA-256:

1. after `grok --no-auto-update version`;
2. after ACP initialize/authenticate.

Any drift fails closed as `BINARY_CHANGED_DURING_PREFLIGHT`; no readiness receipt is emitted. The public executable attestation is the SHA-256 only. This is an anti-race check, not a claim to defeat a privileged adversary capable of atomically swapping and restoring executable bytes between checks.

## Secret/auth and provider-taint boundary

- Grok/xAI remains the OAuth credential owner.
- Mastermind never reads, copies, serializes, logs or transports cached token contents.
- The child environment is allowlisted and excludes `XAI_API_KEY` and token-like environment auth.
- `GROK_HOME` may pass through so an already-approved provider home can be honored, but no home path appears in the public receipt.
- `grok version` output is bounded, internally validated, secret-scanned, then discarded.
- ACP provider wire is bounded and secret-shaped values fail closed.
- **Provider-derived ACP state is control-flow only.** It may select one of a closed set of literal receipt renderers, but no provider-derived value is passed into a renderer or serialized to stdout.
- Every renderer receives only non-provider inputs: stable binary SHA-256 and UTC observation time.
- Exceptional failures publish only fixed `PREFLIGHT_FAILED`; no exception/provider/path/credential-derived text crosses stdout.
- A successful G0 result proves only cached-OAuth ACP readiness for this preflight.
- It does **not** prove every future model invocation is OAuth-only. Current xAI credential precedence can select model-specific credentials before an active session, so the real Worker realm must separately prove the accepted OAuth-only policy/precedence or fail closed.

## Public receipt

`mastermind.grok_build_preflight.v1` contains only:

```text
schema
observed_at
grok_binary_sha256
acp_protocol_version
cached_token_offered
oauth_ready
model_turn_performed=false
executive_routing_ready=false
verdict
reason_codes
```

Positive verdict:

```text
LOCAL_OAUTH_ACP_READY_NOT_ROUTABLE
```

Closed non-ready verdicts:

```text
CACHED_TOKEN_METHOD_UNAVAILABLE
ACP_AUTHENTICATION_FAILED
ACP_INITIALIZE_FAILED
ACP_PROTOCOL_UNSUPPORTED
```

The receipt contains no provider/version text, email, account identifier, token, home path, provider session ID, host-private address, auth-file coordinate, or raw provider output. It cannot be interpreted as Provider Capacity eligibility, Worker claim, Executive routing readiness, model execution proof, or production acceptance.

## Deterministic versus provider behavior

Deterministic Mastermind code owns:

- executable validation/snapshot/revalidation;
- environment construction;
- exact JSON-RPC request bytes;
- closed response parsing;
- secret fences;
- closed ACP outcome enum;
- closed literal receipt rendering;
- process-group cleanup;
- public output.

The provider owns OAuth state, token refresh, advertised ACP auth methods, and authentication success. Provider output has **zero authority** over Executive lifecycle, routing, merge/release, Agent OS, or company completion.

## Failure states

Exceptional/fail-closed states include:

- `BINARY_UNAVAILABLE`
- `BINARY_INVALID`
- `BINARY_CHANGED_DURING_PREFLIGHT`
- `PROVIDER_TIMEOUT`
- `PROVIDER_COMMAND_FAILED`
- `ACP_RESPONSE_INVALID`
- `ACP_PROCESS_EXITED`
- secret-shaped provider wire

Expected ACP non-ready states return only the closed public receipts above. Because G0 performs no model turn or company mutation, provider ambiguity never authorizes retry/failover of an Executive Attempt.

## Accelerated rollout sequence

### G0-A — source implementation

1. land the three-path provider-work-free preflight with focused RED->GREEN tests;
2. require hosted repository CI and current CodeQL/security on the exact head;
3. require independent review confirming no model turn, no credential-content access, no provider-taint serialization, no common-broker/router modification, and no duplicate owner.

Completion: `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

### G0-B — intended-host read-only proof

On the intended Grok Build worker host:

1. resolve the exact installed Grok binary through the approved host/operator path;
2. run the exact accepted preflight once;
3. if cached OAuth is unavailable or authentication fails, stop and diagnose provider-owned login state;
4. only when absent/expired native login is actually established, a human/admin performs provider-native `grok login` or `grok login --device-auth` without exposing OAuth/browser/device secrets to the worker/model;
5. rerun the read-only preflight;
6. accept only `LOCAL_OAUTH_ACP_READY_NOT_ROUTABLE` bound to the exact stable binary SHA-256 with `model_turn_performed=false`.

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
- normal GitHub PR/CI/Sol review;
- no model result may self-authorize merge, release, or next work.

This canary proves useful Grok Build labor can be consumed **before** automatic Executive placement is ready.

### G0-D — immediate manual capacity exploitation

Once the canary is accepted, bounded implementation/research/review waves may preferentially route to the Grok avenue when it is the least-scarce capable route. This remains manual/direct assignment under current routing law and is never mislabeled Executive automatic routing.

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

The already-active CTO-FORGE principal lane owns this critical path. G0 is coordination evidence for that lane, not a second capacity/routing program.

After real G0 evidence, Sol should explicitly adjudicate whether the first real non-Codex PF vertical remains Claude-first, becomes Grok-first, or uses disjoint Claude/Grok canaries after HF1. Do not change PF1 source law implicitly.

## Acceptance tests

Focused source proof must cover:

- absolute regular executable / symlink / missing / executable / size checks;
- stable binary identity and in-place mutation refusal;
- API-key and unrelated-secret environment suppression;
- exact `--no-auto-update version` and `--no-auto-update agent stdio` command allowlist;
- internal version validation with zero provider-version publication;
- exact ACP initialize request and protocol v1 check;
- exact cached-token headless authenticate request;
- cached-token missing / protocol mismatch / malformed / duplicate auth-method refusal;
- authentication success and typed failure outcomes;
- secret-shaped provider-wire rejection;
- five closed public receipt renderers with no provider-derived parameters;
- receipt invariants `model_turn_performed=false` and `executive_routing_ready=false`;
- fixed/opaque exceptional output;
- transcript proof that only `initialize -> authenticate` is emitted, never session/prompt methods.

A host receipt is required before claiming local OAuth/ACP usable. A real bounded Grok coding result through GitHub/CI is required before claiming the Grok avenue operationally useful. Neither proves automatic Executive routing.

## Stop condition

This source carrier stops after exact-head CI/security/review with the three-path G0 implementation. It does not execute host login, perform a model turn, modify Capacity/RF1/HF1/PF1, create a Grok Worker alias, install a service, or generalize routing.

## Continuation handoff

Return to Sol with:

- exact protected pickup and exact G0 head;
- exact three-file census;
- focused local + hosted CI/security receipts;
- independent review verdict;
- any official Grok CLI/ACP contract drift discovered;
- explicit confirmation of zero model prompt, zero Executive lifecycle effect, zero credential-content handling, zero raw provider-text publication, and stable binary identity;
- the exact host action required next: G0-B preflight, or provider-native human login/repair only after the read-only result establishes cached OAuth is unavailable or cannot authenticate.
