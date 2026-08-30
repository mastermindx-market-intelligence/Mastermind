# SCF-CAP1 — Sol Capability Introspection Core

**Operation:** `mastermind-sol-capability-fabric-cap1-20260830-sol-001`  
**Parent:** `mastermind-sol-capability-fabric-20260830-sol-001`  
**Protected pickup:** `mastermindx-market-intelligence/Mastermind@98bc7a71dcd70947c7a18eb5af7493a2f62a2571`  
**Cognition:** `COGNITION_ROUTE: CHAT_PRO_DEFAULT`  
**State at candidate source:** `BUILT_NOT_PROVEN / PRODUCTION_INERT`

## 1. Observable mission

Given immutable, source-owned capability/app/dependency facts, emit one deterministic,
secret-free `mastermind.sol_capability_status.v1` packet that distinguishes technical
availability, write serviceability, production arming, scope sufficiency, dependency health and
company capability proof state.

This lets Sol answer “what can this exact surface safely do now, and why not?” without treating a
configured plugin, broad OAuth scope, merged source file or model assertion as live authority.

## 2. Architecture and owner preservation

CAP1 is a **pure projection**, not a registry.

Existing owners remain authoritative:

- `control_plane.executive_agent_capabilities.ExecutionCapabilityRegistry` owns reviewed execution
  profiles and policy digests;
- Executive OS owns Job/Attempt/Worker/Event and CEO admission;
- RuntimeBinding/SessionTargetRegistry own exact current surfaces;
- each app/connector owner supplies current availability, scopes, generation and proof facts;
- Agent OS owns durable workstream/decision/discovery/handoff;
- GitHub owns implementation/evidence.

The projector performs no discovery and no registration. It cannot arm a profile, add a capability,
select a provider/account, mint a credential, mutate Executive state or persist observations.

## 3. Exact carrier

```text
control_plane/sol_capability_status.py
tests/test_sol_capability_status.py
docs/superpowers/plans/2026-08-30-sol-capability-fabric-cap1.md
```

No config, existing capability registry, OAuth/app, plugin/MCP, service, workflow, Executive,
RuntimeBinding, Wake, Capacity, Slack, Linear or deployment path changes.

## 4. Closed input facts

`CapabilityFact` carries:

```text
name
app_id / app_generation
privilege_class = R0_OBSERVE | W1_ROUTINE | W2_CONSEQUENTIAL | A3_ADMIN
production_armed
required_scopes / current_scopes
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
issue codes[]
```

`DependencyFact` carries one owner-authored current dependency state, availability, source reference
and issue codes. Facts are immutable tuples and closed enums. The projector does not parse prose,
URLs, environment, credentials or provider/account hints.

## 5. Output contract

The envelope includes:

```text
schema = mastermind.sol_capability_status.v1
capability_generation
observed_at
capabilities[] sorted by name
envelope issues[]
canonical_digest
```

Every capability exposes:

```text
name
app_id / app_generation
privilege_class
availability = AVAILABLE | READ_ONLY | DEGRADED | UNAVAILABLE | UNKNOWN | REFUSED
production_armed
required/current/missing scopes
confirmation/prepared-action requirements
canonical_owner
dependency states
schema_digest
proof_state
last_proven_at
read_serviceable / write_serviceable
source_refs
issues
```

The digest is SHA-256 over canonical sorted JSON excluding the digest field itself.

## 6. Deterministic projection law

- `REJECTED_BY_DESIGN` is always `REFUSED`.
- `NOT_BUILT`, `SPEC_ONLY` and `BROKEN` cannot become available from OAuth scope or model prose.
- source code without current live proof remains `BUILT_NOT_PROVEN`.
- a read-only capability may become `PROVEN_LIVE` from an explicit current live-proof fact even when
  write production arming is false.
- a write-capable capability with `production_armed=false` is never write-serviceable; if reads remain
  serviceable it reports `READ_ONLY` and cannot exceed `BUILT_NOT_PROVEN` as a write capability.
- missing required read scope makes the capability unavailable; missing only write scopes may retain
  read serviceability but reports `READ_ONLY / PARTIAL`.
- missing/broken/disconnected/partial/unknown required dependencies remain explicit and fail closed.
- unavailable observation never becomes a false-green empty default.
- duplicate capability names or dependency names are input conflicts.
- output order and digest are permutation-stable.

No score, probability, model ranking or inferred authority is used.

## 7. Data, time, null and correction law

The caller supplies `observed_at`; the projector never calls the clock. `last_proven_at` must include a
timezone when present. `observed_available=null` means unknown, not false or available. Missing facts
remain typed missing.

A later corrected owner observation produces a new packet/digest; CAP1 keeps no history and rewrites no
owner truth. Cross-session durability belongs to the owner’s existing records, not this projector.

## 8. Secret and authority boundary

Input identifiers, scopes, source references and issue codes are bounded. Known access-token,
authorization-header, password, private-key and bearer-token shapes are rejected before projection.
The result contains no raw exception, log, environment, OAuth token, provider account or credential.

A capability status is evidence, not organizational permission. `write_serviceable=true` still does
not replace current Chairman intent, exact action target, prepared-action/current-source gates or
owner-native effect reconciliation.

## 9. RED→GREEN acceptance matrix

- built source without live proof remains `BUILT_NOT_PROVEN`;
- current live read can project `PROVEN_LIVE` without implying write arming;
- broad scopes plus `production_armed=false` remain unavailable for writes;
- missing write scope preserves only read serviceability;
- missing required dependency becomes `DARK_OR_DISCONNECTED`;
- partial dependency remains `PARTIAL / DEGRADED`;
- unknown availability remains `UNKNOWN`;
- rejected surface remains `REJECTED_BY_DESIGN / REFUSED`;
- duplicate capability/generation and duplicate dependency fail closed;
- permutation-stable output/digest;
- secret-shaped source/issue refusal;
- current `ExecutionCapabilityRegistry` remains the source owner and its production-disarmed write
  profile projects honestly;
- output includes every catalog-required field and is secret-free.

## 10. Proof and promotion

Required exact-head proof:

```text
python -m pytest -q tests/test_sol_capability_status.py
python -m pytest -q tests/test_executive_agent_capabilities.py
python -m py_compile control_plane/sol_capability_status.py tests/test_sol_capability_status.py
full protected repository test/security checks
exact three-path census
independent exact-head review
```

The source candidate stops at `BUILT_NOT_PROVEN / PRODUCTION_INERT`. It creates no live
`capability_status` app/tool, connected source gatherer, OAuth enforcement, plugin UI or production
proof. A later SCF app wave must supply real current facts, exact app identity/scopes and a real Chat
call before this can become `PROVEN_LIVE` as a user capability.

## 11. Stop and successor boundary

Stop after exact-head review and guarded records/source merge. Do not start S1, GH2, UI1 or any
write-capability arm from this carrier. No successor inherits START.
