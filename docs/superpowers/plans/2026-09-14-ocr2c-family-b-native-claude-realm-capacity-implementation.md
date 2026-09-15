# OCR-2C Family B — Native Claude Realm Capacity Implementation Plan

**Date:** 2026-09-14  
**Operation:** `ocr2c-family-b-native-claude-realm-capacity-architecture-20260914-sol-001`  
**Status:** `IMPLEMENTATION PLAN CANDIDATE / RECORDS ONLY / NO START`  
**Depends on:** accepted Family B architecture record from this same candidate; current protected HF1/Capacity/OCR source at each later START.  
**Primary owners:** Macro Shared AI Provider Control for capability identity/generation and capacity normalization; Mastermind provider-realm owner for exact native custody binding; existing HF1/Executive/RuntimeBinding owners for execution.

## Goal

Deliver the smallest safe vertical that turns direct `claude.ai` Claude Code logins into governed native execution realms that canonical Capacity can later select, without mapping them to numbered Macro OAuth slots, exposing provider identity/credentials, or creating a second scheduler.

The plan intentionally separates **capacity identity/custody**, **bounded Worker execution**, **persistent Operator execution**, **browser**, and **computer use**. The latter three cannot be used as evidence that the first is complete.

## Current source that must be reused

At the architecture basis:

- `ops/executive_os/claude-worker-preflight.py` is the single provider-work-free native Claude preflight family.
- `ops/executive_os/claude-realm-set-verify.py` validates current distinct host/principal realm observations.
- `ops/executive_os/provider_realm_facts.py` contains the existing owner-minted `ProviderRealmEnrollmentReceipt` pattern.
- `control_plane/subscription_canary_admission.py` already composes owner-minted Capacity and realm evidence for a bounded canary; raw caller booleans are not authority.
- HF1-B/C/D and subscription harness bindings are protected source.
- Macro `engine/provider_capacity.py` owns `mastermind.provider_capacity.v1` and must remain the sole capacity normalizer and provider-capability identity owner.
- OCR-4A provider-neutral rich Operator Harness work is independent and path/scope-disjoint from this contract wave.

Before every implementation child, re-pin current protected Mastermind, current Macro main, current Skillpack, open PR path ownership, and the exact producer/consumer interfaces. Do not implement against the SHAs in this planning record if protected source has advanced.

---

## B0 — Protect the cross-repository contract

**Capability unlocked:** one unambiguous producer/consumer law exists before code, so later workers do not independently invent native account identity or patch v1.

**Owner:** Sol / architecture review.  
**Effects:** records only.

Required artifacts:

1. Mastermind Family B architecture + this plan.
2. Macro owner-side architecture/Agent OS amendment confirming Shared AI Provider Control owns the opaque native `capacity_capability_id`, its generation and the versioned V2 projection.
3. Exact schema-field tables and migration/coexistence law for:
   - Provider-Control native capability identity/generation;
   - `mastermind.provider_realm_enrollment/v2`;
   - `mastermind.provider_native_realm_observation/v1`;
   - `mastermind.provider_capacity.v2`.

Acceptance:

```text
FAMILY_A refusal preserved
v1 unchanged
no ordinal mapping
no PII/secret/path identity
one Provider-Control-owned capability id; no second Mastermind realm id
realm/custody distinctness != provider quota independence
no new scheduler/DB/lifecycle/session plane
current HF1/OCR-4A owner boundaries preserved
```

Stop after current-source independent review and source protection. Only then record `FAMILY_B_ARCHITECTURE_FROZEN`.

---

## B1 — Provider Control native capability identity/generation

**Capability unlocked:** the canonical capacity owner can name one native Claude execution/capacity realm without Anthropic account PII.

**Repository:** Macro.

Extend the existing Shared AI Provider Control capability-identity owner; do not create an Executive/Mastermind account registry. Each native realm receives one opaque `capacity_capability_id` plus an owner-issued integer generation. The key must not encode account ordinal, email, host path or `claude_code_oauth_N` identity.

The exact durable representation must reuse the existing capability manifest/Provider Control ownership surface or a reviewed versioned successor. Do not add a runtime account database merely to issue keys.

RED-first discriminators:

```text
caller cannot choose/forge capability id
caller cannot decrement/reuse stale generation
number/name/config path cannot derive capability id
provider PII/secret fingerprint cannot enter identity
same capability id cannot have two current generations
existing static v1 capability ids remain unchanged
```

No real provider login is required in B1.

---

## B2 — Provider-neutral realm enrollment v2 custody binding

**Capability unlocked:** Mastermind can bind the owner-issued native capability generation to one exact managed host/principal/config custody without minting a competing identity.

**Likely owning paths after current-source revalidation:**

- evolve/extract the existing provider-realm owner behind `ops/executive_os/provider_realm_facts.py`;
- provider-neutral owner implementation under `control_plane/` rather than adding a second native-Claude registry;
- focused tests for receipt construction, seal, generation, wrong-host/principal/custody substitution, stale receipt and v1 coexistence.

The v2 receipt consumes an owner-issued `capacity_capability_id + realm_generation` fact from Macro Provider Control. It cannot originate either value from a Worker request.

RED-first discriminators must prove:

```text
caller cannot mint/forge receipt
caller cannot choose generation
same receipt cannot be rebound to another host/principal/custody
raw config path is rejected from public wire
account email/id/org/token/keychain material rejected
wrong/stale Provider-Control capability receipt rejected
logout/re-enrollment fixture invalidates old generation
ordinary provider token refresh does not require capability rename
v1 consumer continues to validate unchanged
```

No real login is required in B2.

---

## B3 — Claude preflight successor/bridge

**Capability unlocked:** the existing provider-work-free preflight can attest the current managed capability generation/custody context without becoming a capacity owner.

Preserve one preflight family. Do not add `claude-native-preflight-2.py` beside the existing owner. If new wire fields are required, create an explicitly reviewed V2 of the same family with a compatibility rule in the realm-set verifier.

The preflight may consume trusted opaque expected values:

```text
capacity_capability_id
realm_generation
host_ref
os_principal_ref
config_custody_ref
```

It must prove only what it can observe safely:

```text
exact Claude binary/version
worker execution context
native claude.ai auth selected
logged-in readiness
stronger API/cloud/helper/profile auth did not win
current process principal matches trusted principal seam
```

It must not emit raw `CLAUDE_CONFIG_DIR`, email/account/org, Keychain item name/content, provider token, or quota guess.

Provider docs and the installed binary must both be re-attested at implementation time. The current design specifically relies on provider-documented config-directory-specific Keychain custody; version drift that changes this behavior is a typed blocker.

---

## B4 — Macro native realm observation owner + Provider Capacity V2

**Capability unlocked:** Shared AI Provider Control can normalize native Claude realm health/cooling/quota evidence beside existing sources while preserving v1.

**Repository:** Macro.  
**Likely source owner:** `engine/provider_capacity.py` plus the existing provider health/cooling source owners; exact paths selected only after current-source archaeology.

Implementation order:

1. RED-first parser/validator for `mastermind.provider_native_realm_observation/v1` keyed by exact owner-issued `capacity_capability_id + realm_generation`.
2. Canonical secret/PII/path rejection and closed enum/null/freshness rules.
3. V2 normalized projection and semantic snapshot hash.
4. V2 native slots use the owner-issued `capacity_capability_id` as their ordinary `capability_id`; do not add another realm/account key.
5. Add closed `realm_binding` carrying generation, enrollment receipt digest and `capacity_independence` (`verified|unknown`).
6. v1 compatibility: existing v1 bytes/semantics remain stable for existing consumers.
7. correction semantics: newer generation invalidates older generation for current placement; historical evidence remains historical.
8. health/outcome/cooling source precedence and staleness.
9. quota horizons remain unknown when unobservable.
10. capability/custody distinctness must not become `capacity_independence=verified` merely because ids or config custodies differ.

Hostile cases:

```text
future/stale observed_at
realm generation rollback
same capability id with conflicting host/principal evidence
unknown fields
raw path / account PII / token-shaped value
NaN/negative quota
percentage without denominator
provider result mislabeled Executive success
duplicate capability observation with incompatible generation
same-subscription possibility represented as independent capacity
```

No provider call is needed to make parser tests green.

---

## B5 — Mastermind Provider Capacity V2 acquisition/owner fact

**Capability unlocked:** Executive placement can consume one strict V2 Capacity snapshot without importing Macro internals.

Current H0/P0/CF2-I stays intact for its frozen source. Implement a bounded successor acquisition/validation seam rather than widening the old H0 contract in place.

The consumer must bind:

```text
capacity schema/version
snapshot semantic hash
generated_at / freshness input
capacity_capability_id + realm_generation
host_ref
capacity source quality
```

and export only the existing owner-minted Capacity fact form required by placement. A host `work_placement_union` is necessary-but-not-sufficient eligibility evidence; it cannot substitute for enrollment or fresh capacity.

Mutation tests must kill:

```text
accept V1 as V2 by structural superset
ignore realm generation
ignore snapshot freshness
turn unknown quota into full quota
rank outside first lawful Model Router tier
accept caller-authored capacity boolean
use provider observation as lifecycle success
```

No native Claude provider turn in B5.

---

## B6 — One managed real native realm canary

**Capability unlocked:** one direct Claude Max login is proven usable through the governed native realm path before four-account rollout.

This is the first effectful provisioning wave and requires fresh explicit action-time gates. It is **not authorized merely by this plan**.

Provisioning target:

```text
one Provider-Control capacity_capability_id + generation
one dedicated Worker OS principal
one provider-private absolute config root
one opaque config_custody_ref
one direct `claude.ai` subscription login
one v2 realm enrollment binding
```

Ceremony requirements:

- login happens locally under the exact principal/config custody;
- no credential/token/account PII enters GitHub/Slack/Agent OS/model context;
- preflight returns native auth ready under Worker context;
- realm binding references the exact owner-issued generation G;
- Macro observation accepts exact G;
- logout/re-enrollment test or safe dedicated test fixture proves G cannot authorize G+1;
- auth precedence test proves a stronger injected API/cloud auth source is refused as native selection;
- zero model work is required merely to prove enrollment if provider readiness evidence suffices.

If any effect response is ambiguous, reconcile that same capability/custody before another login attempt. Do not switch to a second account to escape uncertainty.

---

## B7 — PF1 native Claude bounded Worker

**Capability unlocked:** a real Executive child Job executes through direct Claude CLI subscription auth and returns through the existing Worker lifecycle.

Reuse the existing PF1 provider-free Claude CLI protocol carrier after current-source reconciliation; do not create another parser. Compose through protected HF1 broker/adapter interfaces.

First production shape:

```text
one Executive Attempt
one selected capability id + realm generation
one foreground bounded Claude process
`claude -p` / reviewed structured or stream JSON
explicit tool/capability allow-set
no Chrome
no computer use
no provider-native background supervisor
no transparent retry/fallback model/account
```

Required proof:

- exact admitted capability generation reaches the provider process context;
- one genuinely useful granted filesystem/repo/tool action occurs;
- structured result returns through common Worker result/effect contracts;
- timeout/cancel/provider refusal never becomes `SUCCEEDED`;
- process death does not launch a hidden replacement Attempt;
- wrong config custody fails before provider work;
- no provider PII/credential is serialized.

Capability ceiling after this wave: one native Claude Worker canary, **not** four-account automatic routing.

---

## B8 — Four-realm enrollment and provider canary

**Capability unlocked:** four direct Claude capability realms are individually usable and independently observable as execution custodies.

Provision four exact owner-issued capability ids/generations under the strongest initial isolation: distinct dedicated principals and distinct config custodies. Human provisioning may intentionally assign four known Max subscriptions, but Provider Control must keep **quota independence unknown** unless accepted evidence supports it; Chairman knowledge is not converted into provider-reported numeric capacity fact.

For each capability A-D prove:

```text
unique owner-issued capability id + generation
unique host/principal/custody tuple under accepted isolation policy
native Worker-context auth ready
one bounded provider turn through the same adapter
correct result bound back to selected capability generation
```

Adverse proof:

- log out one realm: only that capability becomes unavailable for new selection;
- re-enroll it: old generation fails;
- inject/observe rate-limit cooling for one realm: new work avoids it without mutating the other three;
- a duplicated-provider-subscription fixture cannot inflate aggregate quota.

---

## B9 — Capacity-selected four-realm placement

**Capability unlocked:** routine new Claude work no longer requires Chairman account selection.

Only after Capacity V2 and four exact capability generations are accepted:

```text
Job
-> Model Router tier
-> exact capability/authority filters
-> V2 capability-generation eligibility
-> host/resource eligibility
-> cooling/quota evidence when known
-> Capacity deterministic fair-share/least-active policy
-> selected Worker / atomic claim evidence
```

Unknown quota remains honest. Do not build local round-robin state in the Claude adapter. If the Capacity owner uses a deterministic tie/fairness policy, the evidence belongs to that owner.

Before START, a definite usage-limit/unavailable observation may cause lawful PRESTART rebinding. After START, RuntimeBinding is sticky. A modifying/effect-unknown operation cannot move accounts/hosts automatically.

Production proof must include multiple independent Jobs, not four manually invoked CLI commands.

---

## B10 — Persistent Fable/Opus Operator lane

**Capability unlocked:** long-running Claude COO orchestration moves from app windows into Agent Fabric.

Dependency: accepted OCR-4A rich provider-neutral Operator Harness plus B9 core realm/capacity path.

Use provider-native background/session controls only as **process/session mechanisms**. They never own Job lifecycle, retry, queue, routing or failover.

RuntimeBinding must bind the exact:

```text
Executive Attempt
capacity_capability_id + realm_generation
host/principal
Operator Harness generation
provider native session/background-agent id
capability/tool generation
```

First canary should disable or constrain provider-native carried-over background work that could outlive the Mastermind effect boundary. Resume/restart semantics require explicit reconciliation tests before unattended use.

---

## B11 — Browser and computer-use capabilities

These are separate scarce-resource waves after core cutover.

### Browser

Claude-in-Chrome may be admitted as one implementation of the existing BrowserResource capability. First canary is one realm + one host + one exact browser/profile lease. Test config-root/native-messaging contention before multi-realm concurrency. Do not make Chrome the company browser control plane.

### Computer use

Native computer use is a host-scoped leased resource, not an ordinary tool. First canary requires one persistent interactive Claude session, exact host permission state, explicit resource acquisition/refusal/release, and restart/reapproval behavior. Headless Worker success does not prove GUI autonomy.

The preference order for unattended operation remains:

```text
native API/MCP
-> shell/file tools
-> browser
-> computer use
```

---

## Cutover policy

Do not perform a flag-day migration from cloned Claude apps.

```text
SHADOW      native capability/capacity facts visible, app still primary
CANARY-1    one native bounded Worker
CANARY-4    four native Worker realms
SMALL-FLEET Capacity selects normal bounded Claude work
OPERATOR    persistent Fable/Opus through OCR-4A
BROWSER     provider-native browser as leased capability
GUI         computer-use as scarce host capability
CUTOVER     cloned apps no longer critical path; retain one normal Desktop install as break-glass/manual cockpit
```

Rollback at every stage is disabling new placement/admission, not deleting history or replaying ambiguous Attempts.

## Acceptance and production proof

Core CLI migration is `PROVEN_LIVE` only after a real Chairman-level request reaches a useful result through:

```text
Executive Job
-> lawful model tier
-> Capacity-selected exact native Claude capability generation
-> admitted HF1 execution
-> useful Mastermind tool use
-> canonical result/effect receipt
```

and the multi-realm failure matrix proves no Chairman account selection, no cloned-app dependency, no hidden retry, no stale generation, and no false quota aggregation.

Persistent operator, browser and GUI each have their own later `PROVEN_LIVE` gate.

## Stop conditions

Return to Sol instead of proceeding when:

- protected source or incumbent path ownership materially changes;
- Family B cross-repository architecture is not yet independently accepted/protected;
- a required owner can only be satisfied by a second database/scheduler/session/credential plane;
- provider docs/version no longer support the custody assumption being used;
- a realm/login/provider effect is ambiguous;
- a required provider-capacity fact can only be obtained by persisting provider PII/secret fingerprints;
- a modifying Attempt has STARTed and another realm/host is being proposed without canonical reconciliation;
- Browser/GUI work begins to widen the core capacity-identity wave.

## Exact next implementation action after architecture protection

Start **B1 only**: Provider-Control native `capacity_capability_id + realm_generation` source/contract with RED-first identity/forgery/generation tests, preserving v1. In parallel only where source paths are genuinely disjoint, Mastermind may prepare B2 tests after the owner-side identity contract is protected. Do not start PF1 provider work, account enrollment, browser or computer-use from this records plan.