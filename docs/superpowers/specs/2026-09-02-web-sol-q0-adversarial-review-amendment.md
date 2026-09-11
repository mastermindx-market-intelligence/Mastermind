# Web-Sol Pro Usage Observability — Q0 Adversarial Review Amendment

**Date:** 2026-09-02  
**Owner:** Sol, AI CEO  
**Operation:** `web-sol-pro-usage-observability-20260902-sol-001`  
**PR under review:** Mastermind #364  
**Reviewed PR head before this amendment:** `95bc0a3f38e70132446b3c6b7d1336914314b1fd`  
**Current protected Mastermind review pin:** `24fa9bc4acfbffb77f09193dd50d1ee8f90bcbf8`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1  
**State:** `RECORDS_ONLY / SPEC_ONLY / PRODUCTION_INERT`.

## 0. Authority and precedence

This is a later Sol adversarial-review amendment inside the same logical WSX-Q0 operation/carrier. It closes architecture gaps discovered after the initial law/design/plan and the shared-capacity-pool amendment were drafted.

For this PR, read the source packet in this precedence order when wording conflicts:

1. `docs/EXECUTIVE_WEB_SOL_USAGE_CAPACITY_LAW.md` for the parent ownership/security/anti-evasion constitution;
2. `docs/superpowers/specs/2026-09-02-web-sol-shared-capacity-pool-amendment.md` for realm-slot versus shared-resource topology;
3. **this amendment** for the current Web-Sol action-surface, local-count coverage, entitlement-generation and repair rulings;
4. `docs/superpowers/specs/2026-09-02-web-sol-pro-usage-observability-design.md` and `docs/superpowers/plans/2026-09-02-web-sol-pro-usage-observability.md` only where not superseded above.

This amendment does not grant implementation or release authority. PR #364 remains DRAFT/HOLD pending independent review and green CI on its exact final head.

## 1. Review findings

Adversarial review against the Chairman outcome found two release blockers in the first architecture packet and two material correctness gaps.

### BLOCKER A — the design accidentally reasoned from a non-existent SEND authority

Current protected Web-Sol `mastermind.web_sol_surface_action.v1` accepts exactly:

```text
INSPECT
FOREGROUND
```

The current extension has no `SEND`, `TYPE`, model-select, prompt-submit, or generic browser-action authority. Existing static/source law deliberately forbids generic SEND-like authority.

The initial design examples nevertheless used:

```text
governed_submission
exact accepted send receipt
possible-send/lost-receipt
```

as if Web-Sol already had a governed submit operation. That is false current-state reasoning and could let a quota-observability wave smuggle in browser mutation authority.

**Ruling:** WSX-Q1/WSX-Q2 may not add SEND/TYPE/model-selection authority. A future independently accepted provider-action capability may later emit an exact governed usage receipt, but quota observability cannot create that capability as a side effect.

### BLOCKER B — the top-level packet did not make shared resource topology load-bearing enough

Current official OpenAI managed-workspace documentation shows that one browser/seat realm may consume a per-seat included allowance and later a workspace-shared credit resource, while workspace/user/group/overage controls can independently block use. The shared-pool amendment correctly froze the topology, but the initial slot-only examples can still be misread in isolation.

**Ruling:** `CapacityRealmSlot`, `CapacityResourcePool`, and proved slot-resource links are mandatory CAP-WEB-F0 concepts. Shared resource state is canonical once, never cloned per browser realm. The shared-pool amendment is a required member of the WSX-Q0 source packet, not optional commentary.

### MAJOR C — identity generation did not cover entitlement changes

A provider realm can keep the same authenticated account while its allowance semantics change, for example:

- Personal Pro $100 -> $200 or the reverse;
- Business Standard <-> Premium seat reassignment;
- workspace usage-period, user/group/workspace limit or spend-control changes;
- a shared credit pool grant/top-up/exhaustion/correction;
- provider rate-card or entitlement-policy changes relevant to an estimate.

`realm_generation` alone cannot safely invalidate those observations because the provider identity did not change.

**Ruling:** capacity design needs a separate entitlement/resource generation boundary. Provider headroom/reset evidence and estimates are valid only against the exact identity **and** entitlement/resource generation used to observe/derive them.

### MAJOR D — a locally exact event is not a complete account-usage counter

A content script or governed action can prove one specific local event. It cannot prove that no usage occurred while the observer was absent, on mobile, in another browser, or through another lawful surface. `41 [EXACT LOCAL]` can therefore be true as “41 accepted local records” while still being incomplete as “41 total Pro turns used.”

**Ruling:** every local aggregate carries explicit scope and coverage. Product language says `recorded/observed submissions`, not `provider turns consumed`, unless provider evidence establishes that equivalence.

## 2. Frozen current-action boundary

Until another accepted source law deliberately changes it:

```text
Web-Sol effectful action vocabulary for this program:
  INSPECT | FOREGROUND

quota-observability browser source:
  passive/bounded observation only

forbidden additions under WSX-Q*:
  SEND | TYPE | CLICK_GENERIC | SELECT_MODEL | SELECT_ACCOUNT |
  NAVIGATE_GENERIC | RETRY_PROVIDER | FAILOVER_ACCOUNT
```

A quota source may never turn a passive signal into a provider-side action merely to improve accounting.

References in the initial design/plan to `governed_submission` or `exact accepted send receipt` are **future-compatible examples only**. They are not an implementation requirement and do not authorize creating a send path. If no independent governed submit capability exists when Q1/Q2 starts, use the passive-observation contract below or leave the exact governed counter absent.

## 3. Local usage observation without SEND

The useful near-term capability is a **content-free local activity meter**, not a provider-quota scraper.

A future Q2 source may observe only a reviewed closed local interaction boundary that requires no provider mutation by Mastermind. Examples that QF0/Q1 may evaluate include:

```text
local_submit_observed
local_generation_started
local_generation_finished
```

The implementation must not read prompt text, response text, conversation content, raw DOM text, account identifiers, cookies/tokens/storage, or network payloads to establish those events.

### 3.1 Reasoning-class attribution

A passive local submit can be attributed to `sol_pro` only if a reviewed bounded, non-content source deterministically proves the selected reasoning class at the submit boundary.

Examples of potentially acceptable source shapes **only after QF0/source review**:

- a fixed semantic/test attribute whose sole value is the selected reasoning class;
- an existing Mastermind action contract from another independently accepted capability;
- a provider-supported machine-readable product state.

Do not read arbitrary rendered text or infer Pro from response latency, duration, output style, model behavior, token count, page title, or generic UI position.

If reasoning class is not proven:

```text
reasoning_class = unknown
```

and no Pro-specific count increments.

### 3.2 Local event identity

For an independently governed action, inherit the existing operation/action idempotency key.

For passive user interaction, Q1 may define a one-page-lifetime local observation id only if:

- the browser event itself occurs once for the actual local user submit boundary;
- one content-script instance attaches one listener per page generation;
- transport replay preserves the same event id;
- provider activity is never retried to recover a missing telemetry event.

A new durable Web-Sol queue/ledger/browser-history store is still forbidden. If telemetry is lost during a crash/disconnect, the aggregate becomes incomplete; the observer does not recreate the provider action.

## 4. Aggregate scope and coverage

A local activity aggregate needs at least these conceptual dimensions:

```text
metric
reasoning_class
scope
count
coverage
observed_from
observed_through
gap_detected
source/evidence
```

Closed initial `scope` vocabulary:

```text
governed_mastermind_actions_only
this_managed_browser_realm_only
provider_account_total
unknown
```

`provider_account_total` requires provider-supported evidence; a browser-local observer may not claim it.

Closed initial `coverage` vocabulary:

```text
complete_for_governed_scope
best_effort_partial
unknown
```

Interpretation:

- `complete_for_governed_scope`: every action in the explicitly governed Mastermind action stream is represented because the canonical operation path itself emits the receipt;
- `best_effort_partial`: recorded passive events are individually real, but observer downtime/out-of-band usage may be missing;
- `unknown`: completeness cannot be established.

A passive browser counter is never silently upgraded to `complete_for_governed_scope` merely because no disconnect was noticed.

## 5. Correct product language

The initial UI example:

```text
Mastermind Pro submits   41 [EXACT LOCAL]
```

is superseded by one of these truthful forms:

```text
Recorded Pro submits     41 [LOCAL / BEST-EFFORT PARTIAL]
```

or, when a separate governed action stream genuinely guarantees completeness:

```text
Governed Pro submits     41 [EXACT / GOVERNED SCOPE COMPLETE]
```

Neither line means `41 provider quota units consumed`.

The primary Control Room card should separately show:

```text
Provider included headroom   <provider value | UNKNOWN>
Provider reset               <provider value | manual | UNKNOWN>
Local recorded Pro submits   <count + scope + coverage>
Shared resources             <proved linked pool(s), once each>
Forecast runway              <estimate + interval + confidence>
```

If exact Personal-Pro headroom is unavailable, the product remains useful by showing known reset evidence, local recorded consumption trend, observed availability/cooling, and forecast uncertainty without manufacturing an exact remainder.

## 6. Identity, entitlement and resource generations

Capacity evidence must not bind only to browser identity.

Conceptually:

```text
CapacityRealmSlot
  capacity_capability_id
  adapter_instance_id
  realm_generation
  entitlement_generation

CapacityResourcePool
  resource_ref
  resource_generation

CapacityResourceLink
  capacity_capability_id
  realm_generation
  entitlement_generation
  resource_ref
  resource_generation
  relationship
  link_evidence
```

### 6.1 `realm_generation`

Advances when the authenticated provider realm/profile binding changes or cannot be proven stable.

### 6.2 `entitlement_generation`

Advances when the same realm's seat/plan/usage-control semantics materially change or cannot be proven stable. Examples include tier/seat reassignment or a limit-period policy change.

This generation is an opaque company-local control value. Web-Sol does not inspect billing/account PII to derive it. It advances through reviewed provisioning/admin evidence or a fail-closed uncertainty transition.

### 6.3 `resource_generation`

Advances/corrects the version of a linked shared resource's entitlement/balance/control semantics. A top-up, new grant, period change, pool replacement, or material correction can create a new generation according to Provider Control source law.

Dynamic observations and forecasts must name the generation(s) they depend on. A generation mismatch makes them stale/invalid; reserialization may not refresh them.

## 7. Current public-source pre-census (not QF0 completion)

Fresh official OpenAI documentation reviewed on 2026-09-02 establishes these architecture inputs:

### Personal Pro

- Pro has two current usage tiers: $100 with 5x Plus usage and $200 with 20x Plus usage.
- some models have separate allowances;
- ChatGPT displays a reset time when that information is available;
- changing Pro tiers changes the allowance, and an upgrade can take effect immediately;
- no documented Personal-Pro API exposing exact current per-model remaining allowance/reset was established in this review.

Architecture consequence: do not encode 5x/20x as an absolute turn denominator and do not use billing-cycle data as quota reset authority.

### Business

- Standard/Premium seats have included advanced-feature usage;
- after included usage is exhausted, eligible activity can use a workspace-shared purchased credit pool when enabled and permitted;
- workspace credit usage is therefore not total Chat activity, because included usage is consumed first;
- changing seat type can change included usage without changing account identity.

Architecture consequence: realm slot != capacity resource pool, and a credit balance is not a per-seat remaining-included allowance.

### Enterprise/Edu

- managed workspaces can have workspace/group/user usage limits and shared credit/overage controls;
- current usage-limit periods may be monthly or aligned to billing cycle, while legacy weekly settings may exist during migration;
- the documented Spend Controls API can read configured usage-limit settings using a scoped ChatGPT Admin key on eligible workspaces;
- a configured usage limit is not automatically live model headroom, and member-facing Work/Codex usage visibility does not imply regular Chat is included.

Architecture consequence: supported Admin APIs are valuable inputs, but each field keeps its documented semantic meaning and cannot be promoted to Personal-Pro or live model-quota truth.

These are time-sensitive public-source findings. WSX-QF0 must revalidate them against the actual company plan/workspace and current docs/product before implementation. This pre-census authorizes no provider call, admin-key creation, browser extraction, or account mutation.

## 8. CAP-WEB-F0 mandatory architecture outputs

The Macro Provider Control architecture wave must now explicitly freeze all of:

1. `CapacityRealmSlot` opaque identity and `realm_generation`;
2. `entitlement_generation` independent of provider identity;
3. `CapacityResourcePool` for shared/seat/workspace/user/overage/provider constraints;
4. proved `CapacityResourceLink` semantics and UNKNOWN linkage behavior;
5. local `ObservedActivitySummary` with scope + coverage, separate from provider quota;
6. provider quota/reset evidence with field-level provenance/freshness;
7. source precedence/correction and generation invalidation;
8. shared-resource deduplication across multiple realm slots;
9. separate spend/budget authority from capacity availability;
10. a versioned Provider Control vNext contract that leaves `mastermind.provider_capacity.v1` semantics unchanged for current consumers.

No Executive/Control Room schema should invent these independently before Provider Control freezes them.

## 9. WSX-Q1/Q2 repair to the release plan

The first local usage contract does **not** require a current governed SEND path.

Q1 should support two source classes while preserving the same no-new-store rule:

```text
governed_action_receipt
  -> exact for the governed action scope, only when such an independently accepted action exists

bounded_local_observation
  -> individually real local event, aggregate coverage best_effort_partial/unknown
```

Q2's initial production-value target should be:

```text
one installed profile
-> passive content-free submit/mode observation if lawfully and deterministically observable
-> profile-local secret-free event
-> no browser/provider mutation
-> no content/account credential extraction
-> truthful scope/coverage
```

If selected Pro mode cannot be proven through a permitted bounded non-content source, Q2 may ship generic local submit telemetry but **must not** call it Pro usage.

The Q2 failure matrix must test observer/transport loss as an **undercount/coverage degradation**, not as a reason to retry a provider submission.

## 10. Discriminating acceptance tests required downstream

The later schema/implementation waves must include tests that kill these specific false claims:

1. add `SEND` to the quota-observer action vocabulary -> reject;
2. infer `sol_pro` from generic generation active state -> reject/UNKNOWN;
3. replay one passive event id -> one aggregate increment maximum;
4. drop one event during observer disconnect -> count is not repaired by provider retry and coverage is not COMPLETE;
5. label browser-local aggregate `provider_account_total` -> reject;
6. change Personal Pro tier/Business seat entitlement without re-auth -> prior headroom/estimate becomes stale by entitlement generation;
7. clone one workspace shared credit balance into two realm slots as separate resources -> reject;
8. mark shared credits available as spend-authorized -> reject;
9. use Enterprise configured user limit as exact current Sol-Pro remaining -> reject;
10. cross `reset_at` and set remaining to 100% without new provider evidence -> reject.

## 11. Review verdict after this amendment

The source architecture remains **SPEC_ONLY**. This amendment closes the self-review blockers in the source packet by making current Web-Sol action authority, shared capacity topology, entitlement changes and local counter completeness explicit.

It does **not** satisfy the independent-review gate, hosted-CI gate, browser proof, provider-source proof, Provider Control implementation, Control Room product proof or production acceptance.

Exact continuation remains:

```text
PR #364 final source packet
-> green hosted CI on exact head
-> independent architecture/source-law review
-> repair if required
-> only then source protection/release ruling
-> then WSX-QF0 on actual supported provider surfaces
```

No worker watcher/dialogue is associated with this self-review edge.