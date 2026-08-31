# Business Sol Surface Convergence — Surface Fabric and Attestation Amendment

**Date:** 2026-08-29  
**Program:** Business Sol Surface Convergence  
**Canonical architecture carrier:** Mastermind PR #234  
**Operation:** `business-sol-surface-convergence-f0-20260829-sol-001`  
**Protected source reviewed:** `mastermindx-market-intelligence/Mastermind@b8f7414e9906d6b5853640a18de68c3b91ffb44b`  
**Skillpack:** `mastermind.sol_skillpack.v1` version `1.0.1`, bootstrap major `1`  
**Capability state:** `SPEC_ONLY / RECORDS_ONLY`  
**Release posture:** `DRAFT / HOLD-FOR-SOL`; no protected-master movement ahead of the current `#245 → #228` serialization

## 0. Precedence and purpose

This amendment supplements and, where it conflicts, supersedes:

`docs/superpowers/specs/2026-08-29-business-sol-surface-convergence-design.md`

It does not replace the parent outcome, authority map, no-rebuild boundaries, or two-plugin experience architecture.

The parent architecture was directionally correct but contained one premise that is no longer current: it assumed ChatGPT exposed no documented conversation-scoped host identifier. Current official OpenAI Apps SDK documentation defines host-provided `_meta` values including:

- `openai/session` — an anonymized conversation identifier intended to correlate calls within one ChatGPT session;
- `openai/subject` — an anonymized user identifier;
- `openai/organization` — an anonymized organization identifier when available;
- `openai/widgetSessionId` — a mounted widget-instance identifier, not a conversation identity.

Those values move exact surface correlation closer to V1. They do **not** establish authority, identity ownership, Chairman status, Sol role, worker ownership, lifecycle state, or permission to modify anything.

This amendment freezes the connection-layer architecture needed to use those values safely without creating another lifecycle, session, identity, memory, release, retry, or control plane.

## 1. Executive ruling

Mastermind does not need a generic super-MCP.

It needs a **stateless, attested Sol Surface Fabric** that composes systems Mastermind already owns:

- Executive OS for Job / Attempt / Worker / Event lifecycle and CEO-intent admission;
- Agent OS for durable organizational workstreams, decisions, discoveries, and handoffs;
- `CeoIngress` for bounded root Job admission;
- `StewardReadPort` and Secretary grounding for read-only company composition;
- `SessionTargetRegistry` and `RuntimeBinding` for logical and rotating responsibility binding;
- Company Dialogue for bounded worker communication;
- Agent Relay, Wake, Slack, and native transports for delivery and attention;
- `ExecutionCapabilityRegistry` for exact capability grants and attestation;
- GitHub for implementation and evidence truth;
- Linear for selected portfolio projection;
- Slack for dialogue, audit, collaboration, and transport visibility.

The Surface Fabric owns none of those truths. It resolves and projects their current intersection for one exact host/app request.

## 2. Adjudication of the Pro-mode architecture handoff

### 2.1 Accepted

The following recommendations are adopted:

1. Host metadata is correlation evidence only.
2. Effective authority is an intersection, never one token or label.
3. The connection layer must be stateless with respect to canonical lifecycle and responsibility.
4. Existing capability registry and RuntimeBinding seams must be extended rather than duplicated.
5. App and plugin generations must be immutable, pinned, and revocable.
6. Read generations may be compared in parallel; modifying generations may not dual-write.
7. Root CEO admission and bound-child action are different authority classes.
8. Every modifying result requires an explicit effect state and same-key reconciliation path.
9. No ambiguous modifying call may be blindly retried or silently failed over.
10. Read composition should use progressive disclosure, explicit source freshness, nulls, degradation, and revisions.
11. Write fan-out is forbidden.
12. Session retirement and continuation must use Agent OS handoff plus RuntimeBinding lease/fence transfer, not a new conversation-memory store.
13. A read-only host-context falsifier is the first live Business experiment.

### 2.2 Modified

The handoff proposed four user-facing plugin packages. That is unnecessary fragmentation.

Mastermind preserves exactly two top-level plugin experiences:

- **`mastermind-sol`** — the Chairman/Sol reasoning and control experience;
- **`mastermind-operator`** — the bounded worker/COO dialogue experience.

The `mastermind-sol` plugin may reference multiple independently governed app generations. Separate authority realms do not require separate top-level plugin packages.

The app realms are:

1. **Steward Read** — company, attention, runtime, evidence, and exception composition;
2. **Surface** — host-context inspection and later exact RuntimeBinding resolution;
3. **Executive** — bounded root CEO-intent admission and status;
4. **Company Dialogue** — bounded action within one already-bound worker operation.

Secretary and other mechanical services remain internal owners or sources unless a later user journey proves that a separate ChatGPT app is independently useful.

### 2.3 Rejected or deferred

The following are rejected or deferred:

- one generic MCP server that proxies every Mastermind system;
- a `business_sessions` database or any second durable session registry;
- treating plugin import, a plugin manifest, app visibility, or model prose as installed-state attestation;
- treating `openai/session`, `openai/subject`, or `openai/organization` as authorization;
- assuming host metadata is present, globally stable, cross-app stable, or impossible to spoof before live falsification;
- a transferable signed Surface receipt in the first probe wave;
- binding, lease, fence, root admission, or child-action authority in the host-context probe;
- automatic write failover or retries across app generations;
- a separate release registry when `ExecutionCapabilityRegistry` can own the grant;
- a separate conversation memory plane when Agent OS already owns durable handoff.

A signed short-lived Surface Context Receipt may be introduced only if a later cross-service journey requires forwarding a projection. It must never become a bearer credential, canonical state, or authorization source.

## 3. Product thesis

### 3.1 Chairman job

From one ChatGPT Business conversation, Chris should be able to:

- see what the company is doing now;
- identify which Sol and worker operations are active, blocked, dark, stale, or awaiting a decision;
- inspect current product/program state without reconstructing it from Slack;
- admit one explicit CEO intent through the canonical Executive boundary;
- observe the difference between `QUEUED`, delivered, acknowledged, started, completed, proven in production, and finally accepted;
- continue a program in a new Sol conversation without stale authority surviving in the old one.

### 3.2 Sol machine job

Each Sol call should be able to determine, without trusting prompt prose:

- exact plugin source generation;
- exact app/server/tool contract generation;
- authenticated OAuth resource, principal, organization, audience, and scopes where applicable;
- available host correlation evidence;
- current RuntimeBinding/lease/fence state;
- exact canonical Job or responsibility state;
- effective read and effect permissions;
- source revisions, freshness, nulls, and degradation;
- whether a modifying effect definitely occurred;
- the one lawful reconciliation path when effect is uncertain.

### 3.3 Moat

The moat is not the MCP protocol itself. It is the company-specific composition of:

- exact organizational and execution state;
- immutable release and capability attestations;
- correction-safe evidence;
- host-aware but non-host-trusting identity resolution;
- bounded authority intersections;
- explicit effect and reconciliation semantics;
- continuous proof from intent through production capability.

## 4. Experience topology

```text
ChatGPT Business conversation
        │
        ├── mastermind-sol plugin
        │     ├── Sol workflow skills
        │     ├── Steward Read app generation
        │     ├── Surface app generation
        │     └── Executive app generation (only for authorized principals)
        │
        └── mastermind-operator plugin
              ├── Operator workflow skills
              └── Company Dialogue app generation
```

Plugin packages remain web-compatible skills/app-reference packages. They do not embed MCP declarations. Remote MCP apps remain independently published, authenticated, deployed, versioned, and revoked.

Importing or installing a plugin does not grant access to any app and does not authenticate a user.

## 5. Authority model

Effective authority is:

```text
Static Capability Grant
∩ Authenticated OAuth Principal + Resource + Audience + Scopes
∩ Trusted Host and Exact App Realm/Generation
∩ Current RuntimeBinding / Lease / Fence
∩ Canonical Job or Responsibility State
∩ Exact Tool Effect Contract
```

No term independently grants authority.

### 5.1 Host evidence

Host values may answer only questions such as:

- did two calls appear to come from the same documented ChatGPT conversation under the same controlled comparison key;
- did the host provide an organization or subject correlate;
- is this mounted widget instance continuous.

They do not answer:

- is the caller Chris;
- is this conversation Sol CEO;
- does this conversation own a responsibility;
- may this conversation admit a Job;
- may this conversation act for a worker;
- may this conversation modify a binding;
- did a prior effect occur.

### 5.2 OAuth evidence

OAuth authenticates the principal and exact resource audience. It does not itself assign Sol role, responsibility, Job ownership, or child-operation authority.

Each realm uses separate resource identifiers, clients, scopes, and server identities even when infrastructure is co-hosted.

### 5.3 Runtime evidence

`RuntimeBinding` remains the sole rotating provider/runtime binding seam. Host correlation evidence may be attached to or resolved through that seam only after the host-context experiment passes and a separately reviewed binding wave defines lease, fence, staleness, and transfer behavior.

### 5.4 Tool evidence

Tool annotations are host hints. Server-side authorization and effect enforcement remain mandatory.

## 6. Host-context handling contract

### 6.1 Raw-value law

The Surface Fabric must not return, persist, or place in general infrastructure logs:

- raw `openai/session`;
- raw `openai/subject`;
- raw `openai/organization`;
- raw OAuth tokens;
- raw prompt bodies by default;
- credentials;
- full company payloads unrelated to the exact response.

Raw host values may exist transiently in process memory only long enough to validate shape and derive a keyed fingerprint.

### 6.2 Fingerprints

A fingerprint is derived with HMAC-SHA-256 over a domain-separated message containing at least:

```text
schema
app realm
generation
field name
raw host value
```

The response exposes only:

- field presence;
- bounded keyed fingerprint;
- HMAC key version/identifier;
- fingerprint scope;
- observation time;
- degradations.

A fingerprint is correlation evidence, not a principal, credential, binding, or authority token.

### 6.3 Key scopes

Production realms default to app-local correlation keys.

For the explicit HC0 cross-app experiment only, two read-only probe app registrations may share one temporary **probe-cohort** HMAC key. That permits equality testing without exposing raw IDs. The cohort key:

- grants no authority;
- is never reused for a modifying realm;
- is not persisted in Git;
- is rotated or destroyed after the experiment;
- does not prove future cross-app stability.

### 6.4 Missing and malformed metadata

Missing metadata is a normal explicit state, not an exception that may be guessed around.

Malformed, oversized, control-character, binary, nested, or unexpected values are refused or marked degraded according to the exact probe contract. No fallback to user-supplied identity is permitted.

## 7. Surface posture model

The Surface Fabric may project these non-canonical postures:

- `UNLINKED`
- `AUTHENTICATED`
- `GROUNDED`
- `SURFACE_IDENTIFIED`
- `BOUND`
- `READY_READ`
- `READY_ROOT_WRITE`
- `READY_CHILD_ACTION`
- `DEGRADED`
- `EFFECT_UNKNOWN`
- `REVOKED`

These are derived projections. The canonical owners remain the systems named by each supporting receipt.

No single posture may be persisted as a rival lifecycle state.

## 8. Effect taxonomy

Every app tool is assigned one effect class:

- `READ_PUBLIC`
- `READ_COMPANY`
- `READ_CANONICAL`
- `ADMIT_ROOT_JOB`
- `ACT_BOUND_CHILD`
- `ADMINISTER_BINDING`
- `DESTRUCTIVE_ADMIN`

Every modifying result uses one effect state:

- `NO_EFFECT`
- `ACCEPTED_NO_EXECUTION`
- `APPLIED`
- `REJECTED`
- `DUPLICATE_SAME_PAYLOAD`
- `CONFLICT_CHANGED_PAYLOAD`
- `EFFECT_UNKNOWN`

For Executive admission:

```text
canonical Job created in QUEUED
= ACCEPTED_NO_EXECUTION
≠ dispatched
≠ delivered
≠ ACK
≠ START
≠ execution
≠ completion
≠ production proof
≠ final acceptance
```

An `EFFECT_UNKNOWN` result blocks blind retry. The caller must reconcile through the same canonical owner and logical operation key.

## 9. Release and attestation architecture

### 9.1 Existing owner

`config/executive_agent_capabilities.json` and `control_plane/executive_agent_capabilities.py` remain the sole capability grant and attestation owner.

The current v3 registry correctly keeps:

- `production_armed=false`;
- plugin grants empty;
- exact MCP server identity/version/tool-schema digests;
- closed profiles;
- no ambient capability authority.

A later F2 wave may evolve that registry schema. It must not create a second registry.

### 9.2 Plugin source attestation

A plugin grant must bind at least:

- capability ID;
- repository identity;
- immutable commit SHA;
- marketplace path;
- plugin root path;
- native manifest digest;
- exact skill inventory and per-file digests;
- required app-reference inventory;
- package generation;
- revocation state.

A plugin cannot attest itself. Repository contents, controlled import/publish receipts, exact workspace policy, and live app handshake evidence must agree.

### 9.3 App generation attestation

An app grant must bind at least:

- app realm;
- app generation;
- published app identity/reference;
- MCP server identity and version;
- exact tool inventory;
- input and output schema digest;
- annotation digest;
- OAuth resource and required scopes;
- transport profile;
- source commit/build digest;
- release state;
- revocation state.

Published Business apps are immutable snapshots. Updating implementation or contract creates and validates a new generation; it does not mutate evidence for the old generation.

### 9.4 Generation transition

Read-only generations may run side-by-side for comparison.

For any modifying effect class:

- exactly one generation is authoritative;
- the old generation is fenced/revoked before the new generation becomes authoritative;
- no dual-write canary is allowed;
- ambiguous calls reconcile against the same generation and canonical owner;
- rollback is an explicit generation transition, not silent endpoint failover.

## 10. Realm boundaries

### 10.1 Steward Read

Purpose: compose useful company, attention, runtime, evidence, and exception state.

Properties:

- read-only;
- progressive disclosure and pagination;
- explicit source owner, revision, observed time, freshness, trust, null, and degradation;
- no generic Agent OS write;
- no lifecycle mutation;
- no Slack-as-truth reconstruction.

### 10.2 Surface

HC0 purpose: inspect host correlation evidence only.

Later purpose: resolve exact RuntimeBinding state and explain readiness/refusal.

Properties:

- read-only through HC0/F6;
- no durable session store;
- no binding administration in the first app generation;
- any later binding administration uses a separately reviewed effect class, scope, lease, fence, and confirmation path.

### 10.3 Executive

Purpose: submit one explicit Chairman-authorized CEO intent to existing `CeoIngress` and read canonical status.

Properties:

- root admission only;
- exact operation key and payload digest;
- creates one canonical `QUEUED` Job and stops;
- no dispatch or execution claim;
- same-key duplicate and changed-payload conflict handling;
- no arbitrary Executive mutation.

### 10.4 Company Dialogue

Purpose: communicate inside one already-bound worker operation.

Properties:

- existing six-tool contract;
- host/server binding supplies operation identity;
- caller cannot select worker, Job, Attempt, channel, thread, or transport;
- dialogue evidence is not lifecycle completion or production acceptance;
- wrong chat, wrong worker, stale fence, sibling Attempt, and unbound calls fail closed.

## 11. Read composition and Control Room

The in-chat Control Room should expose five progressive sections:

1. **Company** — selected programs and responsibilities;
2. **Attention** — blocked, stale, dark, unacknowledged, and decision-needed items;
3. **Runtime** — Jobs, Attempts, Workers, bindings, leases, and explicit lifecycle distinctions;
4. **Evidence** — GitHub implementation/proof, production receipts, and freshness;
5. **Exceptions** — contradictory, unavailable, revoked, degraded, or effect-unknown states.

No one response should dump the whole company payload into the model. Summary tools return stable identifiers and bounded cards; detail tools resolve one exact object with pagination and source receipts.

Write tools never fan out across owners. One call targets one canonical owner and returns one effect envelope.

## 12. Degradation policy

- If Executive write is unavailable, Steward read should remain available.
- If Slack is unavailable, canonical Job state should remain available.
- If GitHub evidence is unavailable, implementation must not be reported as proven.
- If RuntimeBinding is stale, reads may continue with degradation but child modification is refused.
- If app or plugin generation mismatches, modifying calls are refused.
- If host session metadata is absent, the request remains in a lower-trust posture.
- If source freshness cannot be established, the response labels the exact source degraded.
- If OAuth audience, organization, or scopes mismatch, the realm refuses the call.
- If a modifying effect is unknown, the operation enters explicit reconciliation and no retry/failover occurs.

## 13. Session continuation and retirement

A retiring Sol conversation must produce a canonical Agent OS handoff containing:

- responsibility and operation identities;
- current canonical state and evidence;
- exact unresolved decisions and blockers;
- current RuntimeBinding/lease/fence state;
- accepted next action;
- source and release generations.

The replacement conversation:

1. authenticates in the correct realm;
2. recovers canonical state from existing owners;
3. receives or resolves a new RuntimeBinding generation under the exact transfer law;
4. proves the new fence;
5. begins modifying work only after the old conversation loses modifying authority.

No chat transcript is treated as canonical recovery state.

## 14. Revised implementation sequence

The implementation sequence is now:

```text
F0  architecture amendment and current-source freeze
 ↓
F1  read-only OpenAI host-context falsifier
 ↓
F2  installed plugin/app generation attestation in the existing capability registry
 ↓
F3  separate OAuth resources, clients, scopes, and tunnel/deployment boundaries
 ↓
F4  native typed MCP contract v2 pattern
 ↓
F5  authenticated Steward vertical and in-chat Control Room
 ↓
F6  RuntimeBinding surface seam
 ↓
F7  harmless Executive root admission canary
 ↓
F8  exact bound-child action canary
 ↓
F9  complete dialogue return and attention path
 ↓
F10 session continuation, dual-run, Business-first cutover
 ↓
F11 proven subtraction of obsolete manual reconstruction and stale generations
```

The historical P1 plugin package implementation was closed unmerged and its branch reset. It is evidence of a previously reviewed package shape, not current implementation truth. The source package must be recreated from current protected master only after F2 defines exact installed-bundle attestation.

## 15. F1 — host-context falsifier freeze

### 15.1 Observable mission

Build one private, read-only MCP probe with exactly one model-visible tool:

```text
inspect_surface_context({})
```

It reports only pseudonymous host-correlation evidence and release metadata. It writes no state and grants no authority.

### 15.2 Required output

The output schema is `mastermind.host_context_probe.v1` and includes:

- server identity and version;
- app realm and generation;
- contract digest;
- transport profile or explicit absence;
- HMAC key identifier/version and scope;
- observation time;
- presence and keyed fingerprints for documented host fields;
- OAuth resource/scope posture when configured, otherwise explicit absence;
- correlation-only statement;
- bounded degradations.

It never returns raw host IDs.

### 15.3 Deterministic versus empirical behavior

Deterministic:

- schema validation;
- domain-separated HMAC derivation;
- raw-value redaction;
- empty-input enforcement;
- annotation and contract digest;
- failure/degradation taxonomy.

Empirical:

- whether documented host fields are present in the target Business workspace;
- whether the same conversation is stable across repeat calls;
- whether new and forked conversations differ;
- whether two separate probe app registrations receive the same conversation correlate;
- behavior across refresh, reconnect, reauthentication, organization, device, and missing-metadata states.

No unit test may convert an empirical result into `PROVEN`.

### 15.4 Live test matrix

The Business canary records each claim as `PROVEN`, `DISPROVEN`, or `UNKNOWN` for:

- repeat call in same conversation and same app;
- new conversation;
- forked conversation;
- second probe app registration in same conversation;
- page refresh;
- tunnel reconnect;
- app republish/new generation;
- OAuth reauthentication;
- same user in another organization when available;
- another authorized test principal when available;
- missing metadata;
- malformed or unexpected metadata in headless tests.

### 15.5 Stop condition

Stop before any RuntimeBinding write or authority inference.

A positive result only authorizes a separately planned F6 binding seam. A negative or app-local result changes the correlation architecture; it does not justify a fallback session database.

## 16. Subscription and cutover ruling

There are two distinct decisions:

### 16.1 Beta-seat upgrade

Upgrade one Chairman/Sol account to ChatGPT Business Premium when the F1 probe is locally/headlessly green and has a private reachable endpoint ready for app creation.

That upgrade is useful before the full Mastermind OS is complete because it unlocks real app creation, host-metadata falsification, OAuth enrollment, immutable app-generation testing, and in-chat UX iteration.

It is not operational cutover.

### 16.2 Operational cutover

Business becomes the primary Chairman/Sol cockpit only after:

- exact plugin/app generations are attested;
- Steward reads are useful and correction/freshness-safe;
- one harmless Executive admission canary proves exactly one `QUEUED` Job and no execution claim;
- bound-child dialogue proves wrong-session and stale-fence refusal;
- effect-unknown reconciliation works;
- continuation revokes the old modifying fence;
- dual-run evidence shows Business is better than manual Slack reconstruction;
- legacy subtraction is separately reviewed.

## 17. Current release and collision boundary

This amendment is branch-local records work on the existing #234 architecture carrier.

It does not release or merge #234, #236, or any implementation carrier.

Current protected-master serialization remains:

```text
#245 watcher-continuity procedure
→ #228 Executive Steward release
→ later nonurgent architecture/program movement after fresh reconciliation
```

Project Workroom canonical architecture is #240; stale references to #232 are historical metadata only.

Before any BSC merge:

1. reload the then-current protected Skillpack atomically;
2. reconcile the same carrier history-preservingly;
3. repeat collision and exact-file census;
4. rerun fresh exact-head/current-base proof;
5. perform final Sol adversarial review;
6. merge only the exact accepted head under current release authority.

## 18. Capability ledger after this amendment

| Capability | State | Ruling |
|---|---|---|
| Protected Skillpack/bootstrap | `PROVEN_LIVE` as procedure | Continue exact-commit bootstrap. |
| Company Dialogue MCP contract | `BUILT_NOT_PROVEN` | Preserve six tools; production proof remains. |
| Executive MCP / CeoIngress | `BUILT_NOT_PROVEN` | Preserve root admission boundary. |
| Steward contract | `BUILT_NOT_PROVEN` / serialized release pending | Do not bypass #228. |
| Execution capability registry | `BUILT_NOT_PROVEN`, disarmed | Extend in F2; no second registry. |
| RuntimeBinding / SessionTarget | `BUILT_NOT_PROVEN` | Extend only after F1; no session DB. |
| Historical plugin package bytes | `HISTORICAL_BUILT_NOT_CURRENT` | Recreate after attestation freeze. |
| Surface Fabric architecture | `SPEC_ONLY` | Frozen by parent plus this amendment. |
| Host-context probe | `NOT_BUILT` | F1 is next executable vertical. |
| Unified attested operating envelope | `NOT_BUILT` | Requires F1–F10. |
| Generic super-MCP / Business session database | `REJECTED_BY_DESIGN` | Never build without a new Chairman ruling. |

## 19. Exact next action

Author the bounded F1 implementation plan on the existing BSC planning carrier, then create one fresh implementation carrier from current protected master and execute the first discriminating RED test.

No protected-master merge, live app publication, credential enrollment, RuntimeBinding mutation, Executive Job, Slack mutation, Linear mutation, or operational cutover is authorized by this records amendment.