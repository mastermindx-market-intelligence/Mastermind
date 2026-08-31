# SCF-CAP1 — Sol Capability Introspection Core

**Operation:** `mastermind-sol-capability-fabric-cap1-20260830-sol-001`  
**Hardening children:** `mastermind-sol-capability-fabric-cap1-r1-20260830-sol-001`, `mastermind-sol-capability-fabric-cap1-r2-20260830-sol-001`  
**Parent:** `mastermind-sol-capability-fabric-20260830-sol-001`  
**Protected pickup:** `mastermindx-market-intelligence/Mastermind@98bc7a71dcd70947c7a18eb5af7493a2f62a2571`  
**Current compatible procedure at R2:** `mastermindx-market-intelligence/Mastermind@eccf0a3fae8b8597c2ad0bc4f830e31b220415d2`  
**Cognition:** `COGNITION_ROUTE: CHAT_PRO_DEFAULT`  
**State at candidate source:** `BUILT_NOT_PROVEN / PRODUCTION_INERT`

## 1. Observable mission

Given immutable, source-owned capability, app and dependency facts, emit one deterministic,
secret-free `mastermind.sol_capability_status.v1` packet that distinguishes technical
availability, write serviceability, production arming, scope sufficiency, privilege drift,
dependency health and company capability proof state.

This lets Sol answer “what can this exact surface safely do now, and why not?” without treating a
configured plugin, broad OAuth scope, merged source file, future-dated proof or model assertion as
live authority.

## 2. Architecture and owner preservation

CAP1 is a **pure projection**, not a registry.

Existing owners remain authoritative:

- `control_plane.executive_agent_capabilities.ExecutionCapabilityRegistry` owns reviewed execution
  profiles and policy digests;
- Executive OS owns Job, Attempt, Worker, Event and CEO admission;
- RuntimeBinding and SessionTargetRegistry own exact current surfaces;
- each app or connector owner supplies current availability, scopes, generation and proof facts;
- Agent OS owns durable workstream, decision, discovery and handoff truth;
- GitHub owns implementation and evidence truth.

The projector performs no discovery and no registration. It cannot arm a profile, add a capability,
select a provider or account, mint a credential, mutate Executive state or persist observations.

## 3. Exact carrier

```text
control_plane/sol_capability_status.py
tests/test_sol_capability_status.py
docs/superpowers/plans/2026-08-30-sol-capability-fabric-cap1.md
```

No config, existing capability registry, OAuth app, plugin or MCP, service, workflow, Executive,
RuntimeBinding, Wake, Capacity, Slack, Linear or deployment path changes.

## 4. Closed input facts

`CapabilityFact` carries:

```text
name
app_id / app_generation
privilege_class = R0_OBSERVE | W1_ROUTINE | W2_CONSEQUENTIAL | A3_ADMIN
production_armed
required_scopes / required_write_scopes / current_scopes
confirmation_required / prepared_action_required
canonical_owner
dependencies[]
schema_digest
source_state
observed_available
live_proof_current
write_capable
last_proven_at
source_refs[]
issue_codes[]
```

`DependencyFact` carries one owner-authored current dependency state, requiredness, availability,
source reference and issue codes. Facts are immutable tuples and closed enums. The projector does
not parse prose, URLs, environment values, credentials or provider or account hints.

Model-facing cardinality is closed:

```text
capabilities     <= 128
scopes per set   <= 128
dependencies     <= 64
source refs      <= 32
issue codes      <= 64
```

The capability iterable is consumed incrementally and stops with a typed refusal as soon as the
129th item appears; it is never materialized without a ceiling. Each nested collection is validated
before normalization or projection.

## 5. Output contract

The envelope includes:

```text
schema = mastermind.sol_capability_status.v1
capability_generation
observed_at
capabilities[] sorted by name
envelope_issues[]
canonical_digest
```

Every capability exposes:

```text
name
app_id / app_generation
privilege_class
availability = AVAILABLE | READ_ONLY | DEGRADED | UNAVAILABLE | UNKNOWN | REFUSED
production_armed
required_scopes
required_read_scopes
required_write_scopes
current_scopes
missing_scopes
excess_scopes
confirmation_required / prepared_action_required
canonical_owner
dependency_states
schema_digest
proof_state
last_proven_at
read_serviceable / write_serviceable
source_refs
issues
```

`excess_scopes` is evidence of ambient privilege drift only. It does not grant, revoke or infer a
capability. `EXCESS_SCOPE_PRESENT` is load-bearing in the canonical digest so a widened observed
scope set cannot disappear from an otherwise identical packet.

The digest is SHA-256 over canonical sorted JSON excluding the digest field itself.

## 6. Deterministic projection law

- `R0_OBSERVE` is constitutionally zero-effect: any R0 fact with `write_capable=true`,
  `production_armed=true`, nonempty `required_write_scopes`, `confirmation_required=true` or
  `prepared_action_required=true` is contradictory input and fails closed;
- `write_serviceable=true` is impossible for `R0_OBSERVE` even if future code bypasses input
  normalization; only W1/W2/A3 can represent an effect-bearing capability;
- `production_armed=true` requires `write_capable=true`; a read-only capability family cannot carry a
  production write arm;
- a production arm is contradictory when `source_state` is `NOT_BUILT`, `SPEC_ONLY`, or
  `REJECTED_BY_DESIGN`;
- every W2 or A3 write family requires `prepared_action_required=true`;
- every A3 write family additionally requires `confirmation_required=true`; W1 has no universal
  confirmation requirement and W2 confirmation remains owner/action-specific;
- defense-in-depth write projection repeats the W2/A3 prepared-action and A3 confirmation guards, so
  bypassing normalization cannot manufacture `write_serviceable=true`;
- a future W2/A3 family remains representable while disarmed: `write_capable=true`, explicit write
  scopes, required guard flags, `production_armed=false`, and an unavailable/spec-only state;
- a capability whose own source state is `REJECTED_BY_DESIGN` is always `REFUSED`;
- a **required** dependency in `REJECTED_BY_DESIGN` makes the top-level capability
  `REJECTED_BY_DESIGN / REFUSED`; it may not be laundered into generic `BROKEN` or availability;
- an optional rejected dependency remains visible but does not refuse the parent capability;
- `NOT_BUILT`, `SPEC_ONLY` and `BROKEN` cannot become available from OAuth scope or model prose;
- source code without current live proof remains `BUILT_NOT_PROVEN`;
- a read-only capability may become `PROVEN_LIVE` only from an explicit current live-proof fact whose
  `last_proven_at` is present and no later than envelope `observed_at`;
- `last_proven_at > observed_at` yields `LIVE_PROOF_FUTURE`, makes the proof unusable, prevents live
  promotion and write serviceability, and downgrades a claimed `PROVEN_LIVE` state to
  `BUILT_NOT_PROVEN` where the capability otherwise remains readable;
- a write-capable capability with `production_armed=false` is never write-serviceable; if reads remain
  serviceable it reports `READ_ONLY` and cannot exceed `BUILT_NOT_PROVEN` as a write capability;
- the caller supplies an explicit closed `required_write_scopes` subset; CAP1 never infers scope
  authority from names such as `write`, `admin`, `manage` or provider-specific aliases;
- any required scope not explicitly classified as write-only is read-critical and its absence makes the
  capability unavailable; missing only explicit write scopes may retain read serviceability but reports
  `READ_ONLY / PARTIAL`;
- `required_write_scopes` outside `required_scopes`, or any nonempty write-only set on a read-only
  capability, is invalid input and fails closed;
- excess ambient scopes are reported but never counted toward required-scope authority;
- missing, broken, disconnected, partial or unknown required dependencies remain explicit and fail
  closed;
- unavailable observation never becomes a false-green empty default;
- duplicate capability names or dependency names are input conflicts;
- output order and digest are permutation-stable.

No score, probability, model ranking or inferred authority is used.

## 7. Data, time, null and correction law

The caller supplies `observed_at`; the projector never calls the clock. Both `observed_at` and
`last_proven_at`, when present, must be RFC3339 timestamps with timezones. Timestamp comparison uses
their timezone-aware instants, not lexical order.

`observed_available=null` means unknown, not false or available. Missing facts remain typed missing.
A future proof timestamp remains visible in output for diagnosis but cannot authorize promotion.

A later corrected owner observation produces a new packet and digest. CAP1 keeps no history and
rewrites no owner truth. Cross-session durability belongs to the owner’s existing records, not this
projector.

## 8. Secret and authority boundary

Input identifiers, scopes, source references and issue codes are bounded. Known access-token,
authorization-header, password, private-key and bearer-token shapes are rejected before projection.
The result contains no raw exception, log, environment, OAuth token, provider account or credential.

A capability status is evidence, not organizational permission. `write_serviceable=true` still does
not replace current Chairman intent, exact action target, prepared-action and current-source gates,
or owner-native effect reconciliation.

## 9. RED→GREEN acceptance matrix

- built source without live proof remains `BUILT_NOT_PROVEN`;
- current live read can project `PROVEN_LIVE` without implying write arming;
- future-dated proof cannot promote a read or arm a write and emits `LIVE_PROOF_FUTURE`;
- claimed `PROVEN_LIVE` with future proof is downgraded;
- broad required scopes plus `production_armed=false` remain unavailable for writes;
- explicit write-only scope absence preserves only read serviceability;
- write-looking scope names are read-critical unless explicitly classified;
- invalid write-scope partition fails closed;
- R0 write, arming, prepared-action or confirmation contradictions fail closed;
- W2 and A3 writes without prepared-action guards fail closed;
- A3 writes without explicit confirmation fail closed;
- non-write families cannot carry a production arm;
- `NOT_BUILT`, `SPEC_ONLY`, and `REJECTED_BY_DESIGN` sources cannot be armed;
- future disarmed W2/A3 capability families remain representable but unavailable;
- the private projection seam cannot emit a write-serviceable W2/A3 capability with missing guards;
- every capability and nested collection ceiling rejects the first out-of-bounds item;
- excess ambient scope is explicit, sorted, digest-bearing and authority-neutral;
- missing required dependency becomes `DARK_OR_DISCONNECTED`;
- required rejected dependency becomes `REJECTED_BY_DESIGN / REFUSED`;
- optional rejected dependency remains visible without refusing the parent;
- partial dependency remains `PARTIAL / DEGRADED`;
- unknown availability remains `UNKNOWN`;
- rejected surface remains `REJECTED_BY_DESIGN / REFUSED`;
- duplicate capability generation and duplicate dependency fail closed;
- permutation-stable output and digest;
- secret-shaped source or issue refusal;
- current `ExecutionCapabilityRegistry` remains the source owner and its production-disarmed write
  profile projects honestly;
- output includes every catalog-required field and is secret-free.

## 10. Proof and promotion

Required exact-head proof:

```text
python -m pytest -q tests/test_sol_capability_status.py
python -m pytest -q tests/test_executive_agent_capabilities.py
python -m py_compile control_plane/sol_capability_status.py tests/test_sol_capability_status.py
full protected repository test and security checks
exact three-path census
independent exact-head review
```

The source candidate stops at `BUILT_NOT_PROVEN / PRODUCTION_INERT`. It creates no live
`capability_status` app or tool, connected source gatherer, OAuth enforcement, plugin UI or
production proof. A later SCF app wave must supply real current facts, exact app identity and scopes,
and a real Chat call before this can become `PROVEN_LIVE` as a user capability.

## 11. Stop and successor boundary

Stop after exact-head review and guarded source merge. Do not start S1, GH2, UI1 or any write
capability arm from this carrier. No successor inherits START.
