# Sol Capability Fabric — Prepared-Action Token Correction

**Date:** 2026-08-30  
**Operation:** `mastermind-sol-capability-fabric-20260830-sol-001`  
**Carrier:** Mastermind PR #282 / `sol/sol-capability-fabric-f0-20260830`  
**Protected source at correction:** `mastermindx-market-intelligence/Mastermind@620263090fb9f272f763e420ba103b0ff8dc5f31`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Parents:**
- `docs/superpowers/specs/2026-08-30-sol-capability-fabric-design.md`
- `docs/superpowers/plans/2026-08-30-sol-capability-fabric-tool-catalog.md`
- `docs/superpowers/plans/2026-08-30-sol-capability-fabric-program.md`

**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

This records-only correction creates no token implementation, key, credential, service, app, MCP
server, owner mutation, account/workspace effect or production capability.

---

## 1. Narrow precedence

This correction has **Narrow precedence** over only the following parent wording:

1. architecture Section 6 and catalog Section 2.3 where
   `commit_prepared_action(prepared_digest)` appears;
2. any parent sentence implying a digest alone can reconstruct a prepared request while also
   forbidding a prepared-action store;
3. program/F0 and PR metadata that describe the SCF-F0 release delta as exactly four files.

Every reference to `commit_prepared_action(prepared_digest)` is **superseded** by:

```text
commit_prepared_action(prepared_token)
```

The SCF-F0 release scope is now exactly five files: the original architecture, catalog, program and
source-law test plus this correction. All other parent product, authority, privilege, effect,
no-rebuild, implementation-wave and completion laws remain controlling.

---

## 2. Defect found in adversarial review

The parent contract simultaneously required:

```text
commit accepts only a prepared digest
no durable prepared-action store
```

A digest proves equality but does not contain the target, normalized effect, source preconditions,
principal binding or expiry needed to reconstruct and authorize the commit. Implementing that wording
would force one of three unacceptable outcomes:

- create a hidden digest-to-request database, queue or lifecycle;
- ask the model to resupply privileged action fields at commit time, allowing drift;
- treat the digest itself as a bearer authorization token without authenticated contents.

The correct repair preserves the two-turn preview/commit user experience while remaining stateless
and owner-specific.

---

## 3. Correct closed protocol

Each privilege-separated owner app may expose its own namespaced equivalent of:

```text
prepare_action(
  action_kind,
  target_ref,
  requested_effect,
  operation_key,
  expected_source
) -> PreparedActionPreview

commit_prepared_action(prepared_token) -> ActionReceipt
```

`PreparedActionPreview` includes the human/model-readable preview and one opaque
`prepared_token`. It does not return a credential, raw signing material or broader capability.

The `prepared_token` is an **authenticated self-contained expiring token** protected by the exact
owner app generation's reviewed MAC or digital-signature mechanism. The server validates its integrity and expiry before use.

The token binds at least:

```text
token_schema
app_id
app_generation
schema_digest
policy_id
authenticated_principal_digest
operation_key
action_family
target_ref
normalized_requested_effect
normalized_requested_effect_digest
expected_source_and_precondition_digest
privilege_class
confirmation_requirement
issued_at
expires_at
```

The normalized effect is bounded and secret-free because commit accepts the token only. It may not
contain credentials, private keys, access tokens, arbitrary shell/SQL/HTTP/filesystem/browser
instructions, hidden provider-account selection or any field prohibited from model-visible input.

The token is scoped to one app generation and action family. Cross-app verification or a shared
company-wide signing key is forbidden unless a later source law explicitly establishes an existing
canonical owner; V1 uses app-local key custody and verification.

---

## 4. Commit-time authority and revalidation

A valid token is **not organizational authority** and is not a transferable bearer grant. Commit must
also establish, at action time:

1. current OAuth/resource/subject/scope authentication;
2. the same authenticated-principal digest bound in the token;
3. current Chairman intent and the canonical organizational authority required by that action;
4. exact current Sol action target where the action requires Sol authority;
5. unchanged app/schema/policy generation;
6. the same canonical owner, action family, target, operation key and normalized effect;
7. unchanged load-bearing source/precondition state;
8. no unresolved prior effect for the same operation/action/target;
9. current host confirmation when required by the Chat surface;
10. current production arming for that exact action family.

Only then may the owner app issue one owner-native idempotent request. The token never routes across
owners and never selects a credential, account, host, branch writer or RuntimeBinding.

---

## 5. Replay and effect law without another store

There is **no durable prepared-action store**, digest lookup table, token registry, queue, lock,
lifecycle, scheduler or cross-owner action router.

Replay safety comes from the canonical owner's existing operation/idempotency/effect contract:

```text
same operation + same normalized effect
  -> reconcile the same canonical action/receipt

same operation + changed normalized effect
  -> OPERATION_KEY_CONFLICT / NOT_APPLIED

possible crossed mutation boundary
  -> EFFECT_UNKNOWN
  -> same-owner read-only reconcile_effect(...)
  -> zero blind resend or cross-surface failover
```

An expired token is prepared-state expiry only. It says nothing about whether a prior commit crossed
an effect boundary. A caller must reconcile any possibly submitted commit before preparing again.

No global anti-replay database is introduced. Owner-native idempotency and exact current-source
revalidation are mandatory before any action family can adopt this protocol.

---

## 6. Closed failure behavior

Before owner mutation, these are `NOT_APPLIED`:

```text
PREPARED_TOKEN_MALFORMED
PREPARED_TOKEN_INTEGRITY_REFUSED
PREPARED_TOKEN_EXPIRED
APP_GENERATION_MISMATCH
SCHEMA_GENERATION_MISMATCH
POLICY_MISMATCH
PRINCIPAL_MISMATCH
SCOPE_REFUSED
ORGANIZATIONAL_AUTHORITY_REFUSED
ACTION_TARGET_UNRESOLVED
OPERATION_KEY_CONFLICT
ACTION_FAMILY_REFUSED
TARGET_MISMATCH
PRECONDITION_CHANGED
SOURCE_MOVED
PRIOR_EFFECT_UNKNOWN
PRODUCTION_DISARMED
CONFIRMATION_REQUIRED
```

Once the owner-native mutation may have begun, ambiguous transport or response is `EFFECT_UNKNOWN`,
never `NOT_APPLIED`. Reconciliation reads the canonical owner and never resubmits.

Errors are fixed and secret-free. Invalid-token detail, normalized action payloads, principal source
identifiers, MAC/signature material and dependency exceptions are not reflected to the model.

---

## 7. Implementation constraints for later W2/A3 waves

Each future action-family plan must choose and document one reviewed token encoding and integrity
mechanism compatible with its existing app/auth/key-custody architecture. It must not create a shared
SCF token service merely to reuse code.

Required TDD/mutation cases include:

- altered payload, target, operation, principal, source digest, app generation and expiry;
- token from another app/action family;
- malformed/truncated/oversized token;
- unknown/rotated verification key with explicit generation behavior;
- same valid token committed twice with exactly one owner effect;
- token valid but current authority or target lost;
- token valid but source moved;
- response lost after possible owner mutation, with read-only reconciliation and zero resend;
- expired token after no commit versus expired token after uncertain commit;
- secret and arbitrary-command fields absent from the complete token/preview/result surface.

A cryptographically valid token with stale authority or source must fail. A current OAuth session
with an invalid token must fail. Both are required; neither substitutes for the other.

---

## 8. F0 proof and capability boundary

The SCF-F0 test must prove this correction exists and states the new token protocol, superseded old
signature, stateless boundary and honest capability state. Exact-head repository/security checks and
final Sol review remain required.

Protecting this correction makes only the action protocol source law durable:

```text
prepared-action token contract = SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT
```

No later action is safe merely because this file merged. Every owner-specific implementation still
requires its own current-source architecture, isolated carrier, TDD, authentication, action-target,
idempotency/effect, production arming, real canary and acceptance proof.
