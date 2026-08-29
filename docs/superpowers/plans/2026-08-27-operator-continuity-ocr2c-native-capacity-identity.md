# OCR-2C Native Claude Capacity Identity — Falsifier & Evolution Gate Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish one canonical, rotation-safe identity relationship between each native Executive Claude realm and the Shared AI Provider Control capacity evidence that actually belongs to the same paid subscription, so Capacity Fabric can eventually select among Claude realms without ordinal/name guessing, secret exposure, or a second quota plane.

**Architecture:** OCR-2C does not reopen the current CF2-H0/P0/CF2-I source contract and does not add Claude to its pinned three-Codex inventory. First run a read-only **Family A falsifier**: prove whether an already-provisioned native Claude realm and an existing Macro `claude_code_oauth*` capability can be shown to consume the same subscription and remain detectably bound across credential rotation, using only provider-supported secret-free evidence. If that proof is impossible, STOP Family A and freeze a separate Family B cross-repository contract evolution under Shared AI Provider Control; Macro remains the sole capacity normalizer and Mastermind remains a consumer.

**Tech Stack:** existing Macro `engine/provider_capacity.py` / provider-control sources, existing Mastermind CF2 source contract and capacity claim law, exact host/principal realm evidence from OCR-1, canonical JSON/SHA-256, pytest; no provider work call is required merely to establish identity.

**Specs / owner law:**
- `docs/superpowers/specs/2026-08-27-operator-continuity-native-claude-capacity-identity-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-claude-auth-compatibility-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-identity-owner-amendment.md`
- Macro `agentos/workstreams/WS-EXECUTIVE-CAPACITY-FABRIC.md`
- Macro `agentos/decisions/DEC-EXECUTIVE-CAPACITY-FABRIC-OWNERSHIP-AND-CONTRACT.md`
- Mastermind `research/MASTERMIND_EXECUTIVE_CAPACITY_CF2F_CLAIM_EVIDENCE_AND_ACQUISITION_FREEZE_2026-08-25.md`

## Global Constraints

- Current Capacity Fabric sequence remains controlling: existing CF2-H0 installed-host proof -> independent P0 -> CF2-I, then RF1/HF1/PF1 according to current owner law. OCR-2C cannot reopen CF1/CF2-F or mutate current H0 merely to add Claude.
- Current `ops/executive_os/capacity_source_contract.py` is pinned to the accepted producer release and three Codex `CAPACITY_CAPABILITY_IDS`. **Do not widen that frozen H0 object in OCR-2C-A.**
- Current `ops/executive_os/provider_worker_slots.py` is reviewed Codex worker inventory. Do not turn it into a mixed Claude/Codex catalog as a shortcut.
- Native realm label `claude-pro-01` is not equivalent to Macro `claude_code_oauth_1` by number, Slack username, config dir, environment variable, provider name or human intuition.
- No provider account email/id/organization, token/key value, Keychain contents, auth file, secret fingerprint or reversible account fingerprint may enter GitHub, Agent OS, Executive Events or the identity contract.
- Unknown quota/headroom remains unknown. Auth readiness is not quota truth. Stale evidence is not fresh evidence.
- A Worker/provider adapter may report only observations about its own realm. It never ranks workers or mutates another realm's cooling/availability.
- Shared AI Provider Control in Macro remains the sole capacity normalizer/semantic-hash owner. Mastermind must not add a `claude_capacity.json`, quota table, account map, rotation ledger or provider scheduler.
- Any cross-repository schema evolution is a new architecture/contract wave and must be frozen before implementation. Do not improvise a v2 wire inside an implementation PR.

---

## OCR-2C-A — Same-Subscription Capacity-Twin Falsifier

### Task 1: Define the exact evidence required to claim native realm R == Provider Control capability C

**Files:**
- Records/proof only for this task; no runtime source modification.
- If a machine-checkable verifier is later justified, its source belongs in a separately reviewed bounded implementation carrier after the evidence vocabulary is frozen.

**Produces:** `SameSubscriptionCapacityTwinEvidence` design vocabulary with no account PII.

- [ ] **Step 1: Require two independent identity observations**

A positive Family A proof needs a provider-supported, secret-free equality witness observable from both sides:

```text
native Worker realm R
  -> provider-supported stable subscription/enrollment identity observation X

existing Macro capacity capability C
  -> provider-supported stable subscription/enrollment identity observation X
```

The witness must be stable enough for equality but unsuitable for secret reuse. A mere provider name, plan type, ordinal, reset time, quota percentage, model access or human label is insufficient.

- [ ] **Step 2: Require rotation invalidation semantics**

Before Family A can pass, prove what happens when the credential/enrollment behind C changes. At least one must be true:

```text
A. C's canonical capability identity itself changes on enrollment/account rotation, invalidating the old R<->C binding; or
B. a provider-supported non-secret enrollment generation changes and the binding includes that generation; or
C. current owner law supplies another exact, reviewed invalidation witness.
```

If credential replacement can silently point C at another subscription while preserving all durable binding evidence, Family A is `UNSAFE_ROTATION_ALIAS` and must stop.

- [ ] **Step 3: Reject weak proofs explicitly**

Record falsifiers for:

```text
same ordinal only
same Slack/app name
same reset time/window
same usage percentage
same host only
same Claude binary/config
same operator assertion without provider-supported witness
matching secret hash/fingerprint
reading token/account PII to compare
```

- [ ] **Step 4: Return the evidence vocabulary to Sol before any binding implementation**

Return either:

```text
FAMILY_A_EVIDENCE_VOCABULARY_COMPLETE
```

with exact first-party/provider evidence sources and rotation behavior, or:

```text
FAMILY_A_NO_SAFE_EQUALITY_WITNESS
FAMILY_A_NO_ROTATION_INVALIDATION
```

No binding exists merely because the task ran.

---

### Task 2: Run the Family A proof against one actual native realm and one candidate Macro capability

**Dependencies:**
- OCR-1 has one accepted native realm identity/auth-readiness receipt.
- The candidate Macro capability already exists under Shared AI Provider Control.
- No secret/account PII inspection is required.

**Files:**
- Sanitized proof artifact only under the current review-evidence convention if all fields are allowlisted and non-sensitive.
- No current CF2-H0 source/config mutation.

- [ ] **Step 1: Re-pin both repositories and material provider source law**

Record exact current Mastermind protected SHA and Macro main SHA plus the material provider-capacity source identities used by the proof.

- [ ] **Step 2: Observe the native realm witness through its accepted principal**

Use only the provider-supported read-only identity mechanism approved in Task 1. Do not send model work merely to learn identity unless current provider law explicitly requires a provider outcome for capacity evidence; identity proof itself should remain read-only whenever possible.

- [ ] **Step 3: Observe the candidate Macro capability witness through its existing owner**

Use a new read-only observation only if Shared AI Provider Control already exposes it safely; otherwise return `OWNER_OBSERVATION_MISSING`. Do not read the underlying secret from Mastermind or duplicate Macro credential logic.

- [ ] **Step 4: Compare only canonical non-secret observations**

Allowed positive result:

```text
same_subscription = VERIFIED
rotation_invalidation = VERIFIED
```

Anything `UNKNOWN`, stale, conflicting or operator-guessed fails closed.

- [ ] **Step 5: Perform a rotation-drift falsifier without rotating production credentials**

Use fixtures/provider-documented enrollment semantics or a dedicated non-production/test enrollment when available. Prove the verifier rejects a changed enrollment/account witness under the old binding. Do **not** rotate a production Macro/Claude credential simply to satisfy the test.

- [ ] **Step 6: Return one of exactly three Sol gates**

```text
FAMILY_A_ROTATION_SAFE_BINDING_PROVEN
FAMILY_A_NO_SAFE_EQUALITY_WITNESS
FAMILY_A_NO_ROTATION_INVALIDATION
```

A refusal is a successful falsifier result, not permission to weaken identity.

---

### Task 3: Only on FAMILY_A_ROTATION_SAFE_BINDING_PROVEN, freeze the minimal binding representation

**Files:**
- Architecture/plan amendment only first; implementation is a later bounded carrier.

- [ ] **Step 1: Reuse existing identities only**

The minimal binding may name:

```text
opaque Executive Worker/account realm label
existing capacity_capability_id
accepted host_ref where current CF2 law requires it
provider-supported enrollment generation/identity digest only if the owner already defines it as non-secret canonical evidence
```

Do not mint a second account id.

- [ ] **Step 2: Assign canonical ownership**

Provider-capacity equivalence/rotation validity must remain owned by Shared AI Provider Control or an accepted cross-repo contract derived from it. Executive claim evidence may reference the accepted capability ID; it does not own subscription identity.

- [ ] **Step 3: Freeze revocation/invalidation behavior**

A rotated/re-enrolled capacity capability that loses exact equivalence makes the native realm `capacity_identity=UNKNOWN/UNBOUND`, removing it from automatic capacity-aware placement until re-proven.

- [ ] **Step 4: Stop for Sol architecture acceptance before code**

Do not implement the durable binding inside this falsifier task.

---

## OCR-2C-B — Native-Realm Provider Control Evolution (only if Family A refuses)

### Task 4: Freeze a versioned Shared AI Provider Control evolution; do not patch v1 in place

**Release condition:** Family A returned one of the two refusal gates and Sol explicitly releases Family B architecture.

**Files during architecture wave:**
- Macro `research/` / Agent OS decision/workstream amendment as appropriate.
- Mastermind cross-repo consumer spec/plan.
- No runtime implementation until architecture accepted.

- [ ] **Step 1: Preserve the existing v1 consumer**

`mastermind.provider_capacity.v1` and the current H0/P0/CF2-I source acquisition law continue to mean exactly what their accepted version says. Do not silently insert native Claude realm semantics into the old schema/material-source identity.

- [ ] **Step 2: Define a native-realm observation wire into Macro**

The source observation must be secret-free and scoped to the realm itself. Candidate fields, subject to current-source validation, include only facts such as:

```text
opaque realm/capability key owned by Provider Control
host_ref
provider=claude
execution_surface=native_cli_or_agent_sdk
auth_ready tri-state + observed_at/source quality
health/outcome class + observed_at
cooling active/kind/reset evidence when observed
quota horizons with exact/provider_reported/estimated/unknown evidence
```

No Worker authority, Job/Attempt identity or Slack/session identity belongs in Provider Control.

- [ ] **Step 3: Define the next versioned capacity contract**

The new contract must preserve current CF1 laws:

```text
unknown != false/zero/unlimited
freshness is explicit
stale != fresh
host matters
presence != authentication success
provider outcome != Executive completion
secret-free material-source identity
semantic snapshot hash independent of unrelated repo churn
```

Native Claude observations are normalized by Macro beside existing sources, not by a new Mastermind normalizer.

- [ ] **Step 4: Define correction/rotation semantics**

When a native realm login changes or is deprovisioned, Provider Control must be able to invalidate prior capacity identity/readiness without retaining provider account PII. Re-enrollment creates fresh source evidence; stale old evidence cannot continue to rank the realm.

- [ ] **Step 5: Freeze cross-repo consumer evolution**

Mastermind may consume the accepted new version only through a bounded source-acquisition/validation seam. Do not rewrite current H0's pinned producer release. Decide explicitly whether a later CF2 source contract/version is additive after current CF2-I or whether a separately named Capacity Fabric extension owns it.

- [ ] **Step 6: Return architecture to Sol before implementation**

Required gate:

```text
FAMILY_B_ARCHITECTURE_FROZEN
```

with exact producer/consumer schemas, material source paths, null/freshness/rotation behavior and migration/no-rebuild proof.

---

### Task 5: Family B implementation plan after architecture acceptance

This task is intentionally a **plan-generation gate**, not placeholder implementation. After `FAMILY_B_ARCHITECTURE_FROZEN`, write a new exact TDD implementation plan from the accepted producer/consumer schemas and current heads. Do not pre-author source edits against a contract that does not yet exist.

The eventual implementation plan must at minimum cover:

1. Macro RED-first source-observation and provider-capacity normalization tests.
2. Strict versioned schema/canonicalization/material-source hash tests.
3. Null/stale/unknown/rotation/correction/adverse-provider-outcome tests.
4. Zero secret/PII and zero second-normalizer fences.
5. Mastermind consumer RED-first version/acquisition/validation tests.
6. Claim-path proof only after current Capacity Fabric release law permits it.
7. Real one-native-realm observation canary, then two-realm automatic-placement eligibility proof.
8. Rollback/version coexistence and durable Agent OS handoff.

## Acceptance / Stop Condition

OCR-2C is not complete merely because a mapping file exists. It reaches an accepted capacity-identity state only when one of these is true:

```text
A. FAMILY_A_ROTATION_SAFE_BINDING_PROVEN
   + minimal binding architecture accepted
   + later implementation/proof establishes the native realm's canonical capacity_capability_id

or

B. Family A refused
   + FAMILY_B_ARCHITECTURE_FROZEN
   + versioned Macro Provider Control evolution implemented/accepted
   + Mastermind consumer accepted
   + real native realm capacity observation proven
```

Before OCR-5 automatic realm A -> realm B selection, **both participating native realms** must have accepted canonical capacity identity. Before OCR-8 calls five subscriptions a pool, all five counted realms must have accepted capacity identity and current Provider Control evidence. Auth readiness alone is insufficient.